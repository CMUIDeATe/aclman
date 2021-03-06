#!/usr/bin/python3

import datetime
import logging
import os, sys
import subprocess
import csv, json
import re
import xml.etree.ElementTree as ET
import xml.dom.minidom
import urllib.request
import urllib.parse

from aclman.models import *
import aclman.helpers as helpers

from aclman.cli import CliParser

import aclman.api.s3 as S3
import aclman.api.grouper as Grouper
import aclman.api.mrbs as Mrbs
import aclman.api.skylab as Skylab
import aclman.api.zoho as Zoho


# Prologue.
cli = CliParser('ACLMAN')
cli.option('--live', dest='live', action='store_true', default=False, help="run ACLMAN live on production systems")
cli.option('-s', '--sectionfile', dest='sectionfile', metavar='FILE', action='store', default="data/sections.csv", help="specify a path to a CSV section file defining privileges")
args = cli.parse()

if args.live:
  script_begin_time = datetime.datetime.now()
  run_date = script_begin_time.strftime("%Y-%m-%d-%H%M%S")
  import aclman.config.production as config
  import aclman.secrets.production as secrets
  environment = "PRODUCTION"
else:
  # Confirm development runs before beginning, especially since inputs can be large.
  response = input("Begin a DEVELOPMENT run on `%s`? (y/n) " % args.sectionfile)
  if response.lower() not in ['y', 'yes']:
    print("Aborted.")
    sys.exit(1)
  script_begin_time = datetime.datetime.now()
  run_date = script_begin_time.strftime("%Y-%m-%d-%H%M%S-dryrun")
  import aclman.config.development as config
  import aclman.secrets.development as secrets
  environment = "DEVELOPMENT"

# Install a default instrumented URL opener.
instrumented_opener = urllib.request.build_opener(helpers.CustomHTTPErrorHandler)
urllib.request.install_opener(instrumented_opener)

# Establish auth to each API.
S3.set_secrets(secrets.s3_api)
Grouper.set_secrets(secrets.grouper_api)
Mrbs.set_secrets(secrets.mrbs_db)
Skylab.set_secrets(secrets.skylab_api)
Zoho.set_secrets(secrets.zoho_api)
# NOTE: Zoho auth tokens are only valid for an hour, so we separately call
# Zoho.authenticate() closer to when it's needed.

# Configure logging.
log_dir = "log"
log_file = "%s.log" % run_date
helpers.mkdir_p(log_dir)

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
# Set up file-based DEBUG logger.
file_log_handler = logging.FileHandler(log_dir + '/' + log_file)
file_log_handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d:%(levelname)s\t%(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
file_log_handler.setLevel(logging.DEBUG)
logger.addHandler(file_log_handler)
# If not running in production, also log INFO to the console.
if not args.live:
  console_log_handler = logging.StreamHandler(sys.stdout)
  console_log_handler.setFormatter(logging.Formatter('%(message)s'))
  console_log_handler.setLevel(logging.INFO)
  logger.addHandler(console_log_handler)

subprocess.call(["ln", "-sf", log_file, log_dir + "/latest-%s.log" % environment])
if args.live:
  subprocess.call(["ln", "-sf", log_file, log_dir + "/latest.log"])

output_dir = "output"
helpers.mkdir_p(output_dir)
logger.info("ACLMAN script started: %s" % script_begin_time)
logger.info("Environment is: %s" % environment)



# Read in and process the list of sections from the section file.
logger.info("Processing requested list of sections from section file `%s`...." % args.sectionfile)

s = open(args.sectionfile, "r")
sreader = csv.reader(s)
all_sections = []
all_section_privileges = {}
for row in sreader:
  # TODO: Be more robust in how this file is read in.
  # TODO: Allow for comments/header in the section file.
  section = Section(row[0], row[1], row[2])

  if section in all_sections:
    logger.debug("Skipping duplicate section %s" % section)
  else:
    # TODO: Verify that the section actually exists by calling
    # `/course/courses?semester=...&courseNumber=...&section=...`
    # NOTE: For now, we catch this later when we try to look up its crosslists.
    all_sections.append(section)
    # Initialize an empty privileges list for this section.
    all_section_privileges[section] = []
    logger.debug("Added section %s" % section)

s.close()


# Read in and process the privileges associated with each section from the
# section file.
logger.info("Processing associated privileges for %d sections from section file `%s`...." % (len(all_sections), args.sectionfile))

s = open(args.sectionfile, "r")
sreader = csv.reader(s)
all_privilege_types = []
for row in sreader:
  # TODO: Be more robust in how this file is read in.
  # TODO: Allow for comments in the section file.
  section = Section(row[0], row[1], row[2])
  privilege_type = PrivilegeType(row[3], row[4])
  privilege = Privilege(privilege_type, row[5], row[6], [section])

  # First, register the privilege type if it's new.
  if privilege_type not in all_privilege_types:
    logger.debug("Identified new privilege type %s" % privilege_type)
    all_privilege_types.append(privilege_type)
  # Then, register the specific privilege.
  if privilege in all_section_privileges[section]:
    logger.debug("Skipped duplicate privilege for %s: %s" % (section, privilege))
  else:
    all_section_privileges[section].append(privilege)
    logger.debug("Added privilege for %s: %s" % (section, privilege))

s.close()


# TODO: If `section` is discovered not to exist, mark it as not existing and
# remove it from the list of sections, in order to avoid making further calls
# against it.

# Find all crosslisted sections, and copy the associated privileges where
# appropriate.
all_crosslisted_sections = []
logger.info("Finding crosslists of the specified sections and copying privileges....")
for section in all_sections:
  for crosslist_section in S3.get_crosslists(section):
    if crosslist_section in all_sections:
      # If the section already exists, just skip it.  Don't copy the privileges,
      # as others might be explicitly defined, e.g., different privileges for
      # graduate and undergraduate sections.
      logger.debug("Found %s (crosslist of %s); skipping, already defined" % (crosslist_section, section))
    else:
      logger.debug("Found %s (crosslist of %s); adding new section" % (crosslist_section, section))
      all_crosslisted_sections.append(crosslist_section)
      all_section_privileges[crosslist_section] = []
      # Copy the privileges associated with the original section.
      for privilege in all_section_privileges[section]:
        new_privilege = privilege.replace_sections([crosslist_section])
        all_section_privileges[crosslist_section].append(new_privilege)
        logger.debug("  Copied privilege: %s" % new_privilege)

# Add all crosslisted sections to the overall list of sections, then free the
# list of crosslisted sections since we're done with it.
all_sections.extend(all_crosslisted_sections)
del all_crosslisted_sections


# Load the rosters for all sections and bring each student's enrollment data
# into the `all_bioIds` structure, which abstracts each student to their BIO
# ID.
#
# NOTE: We maintain this layer of abstraction for now because getting actual
# data on the students themselves requires a separate API call, which we
# minimize here by coalescing records with the same student BIO ID before
# moving on.
logger.info("Processing rosters for each section....")
all_bioIds = {}
enrollments_by_bioId = {}

for section in all_sections:
  section_roster = S3.get_roster_bioUrls(section)
  enrollment_count = len(section_roster)
  if enrollment_count == 0:
    logger.warning("%-12s: NO STUDENTS ARE ENROLLED!" % section)
  else:
    logger.debug("%-12s: %2d enrolled" % (section, enrollment_count))

  for enrollment in section_roster:
    # The student BIO URL is a fully-qualified URL.
    bioUrl = enrollment['studentURL']
    # Extract the `bioID` from the `studentURL`.
    pattern = re.compile("/bio/(\d+)\?idType=BIO")
    bioId = pattern.findall(bioUrl)[0]

    # Create a record for the student's BIO ID if it hasn't yet been seen.
    if bioId not in all_bioIds:
      all_bioIds[bioId] = { 'sections': [] }
    # Mark that this student has enrollment in the section being processed.
    # TODO: Fix this data structure so it's useful.
    all_bioIds[bioId]['sections'].append(section)

    # NOTE: The `section_roster` object should, in principle, contain
    # `finalGrade` data for each student, but doesn't in practice.
    # TODO: Request explicit API access to such `finalGrade` data.


# Get data for each student, and record their sections alongside.
logger.info("Getting data for all %d dedup'd students found...." % len(all_bioIds))
for bioId in all_bioIds:
  # Keep track of this student's enrolled sections.
  sections = sorted(all_bioIds[bioId]['sections'])
  student = S3.get_student_from_bioid(bioId)

  if student:
    logger.debug("%-8s - %-28s\t%s" % (student.andrewId, student.allNames,
      ','.join(str(x) for x in sections)))
    # Record this student's data and their sections.
    S3.students[student.andrewId] = student
    S3.student_sections[student.andrewId] = sections
  else:
    logger.error("Did not find data for BIO ID '%s'" % bioId)

# Free the dictionary of BIO IDs since we're done with it.
del all_bioIds


# Determine each student's privileges.
logger.info("Computing privileges for %d students...." % len(S3.students))
all_student_privileges = {}
coalesced_student_privileges = {}

for andrewId in sorted(S3.students.keys()):
  student = S3.students[andrewId]
  logger.debug("%-8s - %-28s" % (andrewId, student.allNames))
  all_student_privileges[andrewId] = {}

  for section in S3.student_sections[andrewId]:
    for privilege in all_section_privileges[section]:
      privilege_type = privilege.privilege_type

      if privilege_type in all_student_privileges[andrewId]:
        all_student_privileges[andrewId][privilege_type].append(privilege)
      else:
        all_student_privileges[andrewId][privilege_type] = [privilege]

  # Coalesce privileges of the same type.
  # NOTE: This returns a single privilege for each type, with the maximal time
  # range currently valid, if any; otherwise, the next future range if one
  # exists; otherwise, one in the recent past.
  coalesced_student_privileges[andrewId] = []
  for privilege_type in all_student_privileges[andrewId]:
    privileges = all_student_privileges[andrewId][privilege_type]
    try:
      while len(privileges) > 1:
        a = privileges.pop()
        b = privileges.pop()
        p = a.coalesce(b)
        privileges.append(p)
      # Extend the list of coalesced privileges with the resulting
      # single-element list.
      coalesced_student_privileges[andrewId].extend(privileges)
    except ValueError:
      logger.warning("ValueError when attempting to coalesce privileges %s and %s" % (a, b))
      # If for some reason we tried to coalesce unlike privileges, just find
      # any one that is current.
      for privilege in privileges:
        if privilege.is_current():
          coalesced_student_privileges[andrewId].append(privilege)
          logger.warning("  Used %s as the coalesced representative for %s, because it is current" % (privilege, privilege_type))
          break
      # If none are current, take the first.
      coalesced_student_privileges[andrewId].append(privileges[0])
      logger.warning("  Used %s as the coalesced representative for %s, since none were current" % (privileges[0], privilege_type))

  for privilege in coalesced_student_privileges[andrewId]:
    logger.debug("  %s" % privilege)

# Free the nested dictionary of individual privileges since we're done with it.
del all_student_privileges



# Now that we have calculated the set of privileges for each student, generate
# various outputs.



#   0. Generate and store locally a JSON representation of the calculated data.
#        - TODO: Check diffs between the current version of this data and the
#          most recently cached version before determining what actions should
#          be taken on any downstream systems.
jsondata_dir = "%s/jsondata" % output_dir
jsondata_file = "data-%s.json" % run_date
jsondata_path = jsondata_dir + '/' + jsondata_file
helpers.mkdir_p(jsondata_dir)
logger.info("Generating JSON file to locally cache calculated data at `%s`...." % jsondata_path)

all_data = {}
for student in S3.students:
  all_data[student] = {
    'academic': S3.students[student].data['academic'],
    'biographical': S3.students[student].data['biographical'],
    'privileges': coalesced_student_privileges[student],
    'sections': S3.student_sections[student]
  }

# Write out the file.
with open(jsondata_path, 'w') as jsonfile:
  jsonfile.write(json.dumps(all_data, sort_keys=True, indent=2, cls=helpers.CustomJSONEncoder))
jsonfile.close()
subprocess.call(["ln", "-sf", jsondata_file, jsondata_dir + "/latest-%s.json" % environment])
if args.live:
  subprocess.call(["ln", "-sf", jsondata_file, jsondata_dir + "/latest.json"])


#   1. Generate XML file for door/keycard ACL management, upload via SFTP with
#      SSH keys to the CSGold Util server.
#        - NOTE: Enrollment data is NOT nominaly needed here, as card expiry
#          will override when necessary, but it will help reduce file size and
#          group size.
keycard_dir = "%s/keycard" % output_dir
keycard_file = "keycard-%s.xml" % run_date
keycard_path = keycard_dir + '/' + keycard_file
helpers.mkdir_p(keycard_dir)
logger.info("Generating XML file for CSGold door/keycard ACLs at `%s`...." % keycard_path)

# Create the root elements of the XML file.
keycard_xml_root = ET.Element('AccessAssignments')
keycard_comment = ET.Comment('Generated as \'%s\' by ACLMAN at %s' % (keycard_file, datetime.datetime.now()))
keycard_xml_root.append(keycard_comment)

# Generate the elements for each access privilege.
for andrewId in sorted(coalesced_student_privileges.keys()):
  for privilege in [x for x in coalesced_student_privileges[andrewId] if x.key == "door_access"]:
    # NOTE: This process will even add old, expired privileges to the file.
    # When they're re-uploaded, such records will live in the patron group for
    # a few hours afterwards before being deleted as expired by the CSGold
    # server.  We can avoid such churn by first checking against a copy of
    # what's already on the server and not adding privileges which are both old
    # and already dropped from the server.  (If, on the contrary, we calculate
    # a privilege as old here, but it is current on the server, we do want to
    # re-upload it, as that's likely been caused by a drop.)
    # TODO: Request access to such a feature, and/or track the server state to
    # calculate diffs.  This would also have the added benefit that we could
    # avoid re-uploading ANY privilege which hasn't changed.
    #
    # NOTE: Don't be too aggressive about cleaning out the patron groups until
    # it has been determined how many legacy users currently retain ad hoc
    # privileges in those patron groups, and those have either been ended (if
    # they're no longer needed) or special-cased in other ways, so they won't
    # be overwritten.
    priv_asgn = ET.SubElement(keycard_xml_root, 'AccessAssignment')

    priv_asgn_andrewid = ET.SubElement(priv_asgn, 'AndrewID')
    priv_asgn_group = ET.SubElement(priv_asgn, 'GroupNumber')
    priv_asgn_start = ET.SubElement(priv_asgn, 'StartDate')
    priv_asgn_end = ET.SubElement(priv_asgn, 'EndDate')
    priv_asgn_comment = ET.SubElement(priv_asgn, 'Comment')

    priv_asgn_andrewid.text = andrewId
    priv_asgn_group.text = config.csgold_group_mapping[privilege.value]
    priv_asgn_start.text = str(privilege.start)
    priv_asgn_end.text = str(privilege.end)
    priv_asgn_comment.text = "ACLMAN-%s: %s" % (run_date, ','.join([str(x) for x in privilege.sections]))

# Write out the file.
with open(keycard_path, 'w') as xmlfile:
  xmldata = xml.dom.minidom.parseString(ET.tostring(keycard_xml_root))
  xmlfile.write(xmldata.toprettyxml(indent="  "))
xmlfile.close()
subprocess.call(["ln", "-sf", keycard_file, keycard_dir + "/latest-%s.xml" % environment])
if args.live:
  subprocess.call(["ln", "-sf", keycard_file, keycard_dir + "/latest.xml"])

# Upload the file via SFTP to the CSGold Util server.
# NOTE: In Python 3.5, the need for an SFTP batchfile should be avoided by
# reading input from stdin, e.g.,
#   subprocess.run(["sftp", "-b", "-", ...], ..., input=...)
# as opposed to `subprocess.call(...)`.
# See https://docs.python.org/3/library/subprocess.html#subprocess.run
logger.info("Uploading XML file for door/keycard ACLs to CSGold Util %s server...." % environment)
batchfile_path = '/tmp/aclman-sftp-batchfile'
with open(batchfile_path, 'w') as batchfile:
  batchfile.write("put %s Drop/" % keycard_path)
batchfile.close()

# Suppress verbose SFTP output with the `stdout=subprocess.DEVNULL` option.
# Errors will still print to stderr.
subprocess.call(["sftp", "-b", batchfile_path, "-i", secrets.csgold_util['ssh_key_path'],
  "%s@%s" % (secrets.csgold_util['username'], secrets.csgold_util['fqdn'])],
  stdout=subprocess.DEVNULL)
# Remove the temp file.
os.remove(batchfile_path)

# TODO: Compare the just-generated ACL file with the previous version and log
# the diffs locally.  This will make the reasons for drops easier to determine
# empirically.


#   2. Populate Grouper group for base community privileges.  In particular,
#      this is an element used in determination of laser cutter access
#      privileges, although a community role can also be sponsored, earned by
#      related IDeATe employment, or earned by workshop participation.  (Users
#      must also complete all required safety trainings for full access.)
#        - NOTE: Enrollment data is NOT nominaly needed here, as account expiry
#          will override when necessary.
base_privileges_group = config.grouper_groups['base_community_privileges']

# Get the existing group members.
logger.info("Getting existing group memberships for `%s`...." % base_privileges_group)
existing_andrewIds = Grouper.get_members(base_privileges_group)

# Calculate who should be in the group based on privileges.
logger.info("Calculating new group memberships for `%s`...." % base_privileges_group)
calculated_andrewIds = set()
for andrewId in sorted(coalesced_student_privileges.keys()):
  for privilege in [x for x in coalesced_student_privileges[andrewId] if x.key == "base"]:
    if privilege.is_current():
      calculated_andrewIds.add(andrewId)

# Determine differences between current and calculated group membership.
logger.info("Determining group membership differences....")
grouper_to_del = existing_andrewIds.difference(calculated_andrewIds)
grouper_to_add = calculated_andrewIds.difference(existing_andrewIds)

# Add and remove members as determined.
logger.info("Removing %d members from group `%s`...." % (len(grouper_to_del), base_privileges_group))
for andrewId in sorted(grouper_to_del):
  try:
    Grouper.remove_member(base_privileges_group, andrewId)
    logger.debug("  Removed %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
  except urllib.error.HTTPError as e:
    sys.stderr.write("  Grouper error while removing member %s: %s\n" % (andrewId, e))
    logger.error("  Grouper error while removing member %s: %s" % (andrewId, e))
logger.info("Adding %d members to group `%s`...." % (len(grouper_to_add), base_privileges_group))
for andrewId in sorted(grouper_to_add):
  try:
    Grouper.add_member(base_privileges_group, andrewId)
    logger.debug("  Added %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
  except urllib.error.HTTPError as e:
    sys.stderr.write("  Grouper error while adding member %s: %s\n" % (andrewId, e))
    logger.error("  Grouper error while adding member %s: %s" % (andrewId, e))


#   3. Generate access lists for room reservation privileges in MRBS; update
#      via direct entries into the MySQL database.
#        - NOTE: Enrollment data is NOT nominaly needed here, as this privilege
#          is only granted for the current semester for HL A10A only.

# Iterate over all 'room_reservation' privilege types.
for privilege_type in all_privilege_types:
  if privilege_type.key != "room_reservation":
    continue
  else:
    mrbs_roomNumber = privilege_type.value
    mrbs_roomId = config.mrbs_room_mapping[mrbs_roomNumber]

    # Get the existing group members.
    logger.info("Getting existing MRBS ACLs for %s (room ID %d)...." % (mrbs_roomNumber, mrbs_roomId))
    existing_andrewIds = Mrbs.get_members(mrbs_roomId)

    # Calculate who should be in the group based on privileges.
    logger.info("Calculating new MRBS ACL memberships for %s (room ID %d)...." % (mrbs_roomNumber, mrbs_roomId))
    calculated_andrewIds = set()
    for andrewId in sorted(coalesced_student_privileges.keys()):
      for privilege in [x for x in coalesced_student_privileges[andrewId] if x.key == "room_reservation" and x.value == mrbs_roomNumber]:
        if privilege.is_current():
          calculated_andrewIds.add(andrewId)
    # Add positive overrides to calculated list.
    # These are typically faculty or student employees who need reservation
    # privileges but would not receive them through enrollment in a course.
    # Get these from Grouper.
    logger.info("Adding positive overrides....")
    mrbs_overrides = Grouper.get_members("Apps:IDeATe:Permissions:Room Reservation:%s - Overrides Positive" % mrbs_roomNumber)
    for andrewId in mrbs_overrides:
      calculated_andrewIds.add(andrewId)

    # Determine differences between current and calculated group membership.
    logger.info("Determining group membership differences....")
    mrbs_to_del = existing_andrewIds.difference(calculated_andrewIds)
    mrbs_to_add = calculated_andrewIds.difference(existing_andrewIds)

    if not args.live:
      # Since there is presently no development environment for MRBS, take no
      # action in DEVELOPMENT mode; rather, simply output the calculated
      # differences.
      logger.info("Environment is %s; NOT adding/removing MRBS users." % environment)
      logger.debug("%d members should be removed from MRBS ACL for %s (room ID %d)...." % (len(mrbs_to_del), mrbs_roomNumber, mrbs_roomId))
      for andrewId in sorted(mrbs_to_del):
        logger.debug("  %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
      logger.debug("%d members should be added to MRBS ACL for %s (room ID %d)...." % (len(mrbs_to_add), mrbs_roomNumber, mrbs_roomId))
      for andrewId in sorted(mrbs_to_add):
        logger.debug("  %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
    else:
      # In PRODUCTION, add and remove members as determined.
      logger.info("Removing %d members from MRBS ACL for %s (room ID %d)...." % (len(mrbs_to_del), mrbs_roomNumber, mrbs_roomId))
      for andrewId in sorted(mrbs_to_del):
        try:
          Mrbs.remove_member(mrbs_roomId, andrewId)
          logger.debug("  Removed %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
        except:
          sys.stderr.write("  MRBS error while removing member %s!\n" % andrewId)
          logger.error("  MRBS error while removing member %s!" % andrewId)
      logger.info("Adding %d members to MRBS ACL for %s (room ID %d)...." % (len(mrbs_to_add), mrbs_roomNumber, mrbs_roomId))
      for andrewId in sorted(mrbs_to_add):
        try:
          Mrbs.add_member(mrbs_roomId, andrewId)
          logger.debug("  Added %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
        except:
          sys.stderr.write("  MRBS error while adding member %s!\n" % andrewId)
          logger.error("  MRBS error while adding member %s!" % andrewId)


#   4. Compare with a dump of existing user lists from Zoho/Quartermaster for
#      Lending Desk privileges, determine diffs, and update Zoho memberships
#      accordingly.
#        - NOTE: Enrollment data is REQUIRED to do this properly, since
#          permissions persist even after a student is no longer
#          contemporaneously enrolled in the course which conferred this
#          privilege.  We accomplish this with the calculated `billable` flag.

# Get a fresh auth token.
logger.info("Getting Zoho auth token...")
Zoho.authenticate()

# Get the existing group members.
logger.info("Getting existing Lending Desk memberships from Zoho....")
zoho_user_data = Zoho.get_users()
zoho_users = {}
existing_andrewIds = set()
for user in zoho_user_data:
  zoho_users[user['user_aid']] = user
  existing_andrewIds.add(user['user_aid'])

# Calculate who should be in the group based on privileges AND whether the
# student is billable.  Lending is provisioned based on the base community
# privileges.
logger.info("Calculating new Lending Desk memberships for Zoho....")
calculated_andrewIds = set()
for andrewId in sorted(coalesced_student_privileges.keys()):
  # XXX-Covid: Lending access is temporarily restricted beyond the normal
  # "base" privilege to the "lending" privilege with special "covid" value,
  # which is limited only to current, ongoing courses.
  for privilege in [x for x in coalesced_student_privileges[andrewId] if x.key == "lending" and x.value == "covid"]:
    # NOTE: Do not consider yet whether the student is billable; handle that
    # below.
    if privilege.is_current():
      calculated_andrewIds.add(andrewId)

# Determine differences between current and calculated group membership.
logger.info("Determining group membership differences....")
zoho_to_add = set()
zoho_to_activate = set()
zoho_to_deactivate = set()

for andrewId in calculated_andrewIds.difference(existing_andrewIds):
  try:
    billable = S3.get_student_from_andrewid(andrewId).billable
  except:
    billable = False
  # If not listed in Zoho, add the user as long as they're billable.
  # NOTE: Since the user is being added due to their enrollment, it is assumed
  # that their role for Zoho should be "Student".
  if andrewId not in existing_andrewIds and billable:
    zoho_to_add.add(andrewId)

# NOTE: Zoho users need not be students, but different roles have different
# meanings within the Zoho lending application and must be handled accordingly
# here although ACLMAN's focus is on student enrollment and whether a student
# is regarded as billable.  In particular, as the Zoho lending application is
# currently built, the `user_role` parameter must be exactly ONE of:
# - Student
# - Staff (meaning a student employee, an operator of the lending application)
# - Teaching Assistant
# - CMU Staff
# - Faculty
# - Admin
#
# Patrons listed as "Student", "Staff", or "Teaching Assistant", when Active in
# Zoho, are assumed to be billable; that is, they have an active Student
# Account with the HUB, which will accept charges posted thereto.  As such,
# these users are eligible to have materials sold directly to them at the
# Lending Desk and billed to their Student Account.  Of particular note,
# "Staff" and "Teaching Assistant" users are provisioned access as part of that
# role, and may or may not have earned lending privileges separately through
# their own IDeATe enrollment as a "Student".  They are expected to retain such
# access while they remain a billable student, unless and until it is manually
# revoked.
#
# Patrons listed as "CMU Staff", "Faculty", or "Admin" are assumed to NOT be
# billable.  As such, late fees are not assessed to Student Accounts for these
# users and direct sales of materials are prohibited by the lending
# application.  It is possible, however, that these users may actually be
# billable for periods when they are simultaneously enrolled as a student (most
# commonly for "CMU Staff"), in which case they should retain general lending
# access for the duration that they remain billable.  Membership in these
# categories is generally provisioned and deprovisioned manually and
# asymmetrically, and membership audits must be conducted regularly by Admins.
#
# TODO: Further work may disentagle the edge cases caused by the actual
# orthogonality of these roles.  For now, copiously warn by logging an error
# upon activating or deactivating users with any role other than "Student".
for andrewId in existing_andrewIds:
  user = zoho_users[andrewId]
  try:
    billable = S3.get_student_from_andrewid(andrewId).billable
  except:
    billable = False
  # If already Inactive, but privilege is calculated as current, reactivate
  # them as long as they're billable.  But log an error/notice if the prior
  # role being restored is anything other than "Student".
  if user['user_status'] == 'Inactive' and andrewId in calculated_andrewIds:
    # Don't reactivate a blacklisted user.
    if user['blacklisted'] == 'true':
      continue
    if user['user_role'] == 'Student':
      if billable:
        zoho_to_activate.add(andrewId)
    elif user['user_role'] not in ['Admin', 'Faculty']:
      if billable:
        zoho_to_activate.add(andrewId)
        logger.error("Notice: User '%s' to be activated; role is %s (user is billable)" % (andrewId, user['user_role']))
    else:
      # "Admin" and "Faculty" roles need not be billable.  Log an error/notice
      # when they're activated in this fashion.
      zoho_to_activate.add(andrewId)
      logger.error("Notice: User '%s' to be activated; role is %s" % (andrewId, user['user_role']))
  # If already Active and role is "Staff" or "Teaching Assistant", the user
  # should generally remain Active as part of that role, regardless of whether
  # they appear in `calculated_andrewIds` from course enrollment as a student.
  # So, take special care to ensure the user remains billable and only
  # deactivate them if they aren't.  Also log an error/notice.
  elif "Active" in user['user_status'] and user['user_role'] in ['Staff', 'Teaching Assistant']:
    # Don't deactivate a whitelisted user.
    if user['whitelisted'] == 'true':
      continue
    if not billable:
      zoho_to_deactivate.add(andrewId)
      logger.error("Notice: User '%s' to be deactivated; role is %s (user is not billable)" % (andrewId, user['user_role']))
  # For other roles, if already Active, but privilege is calculated as not
  # current or the user is not billable, deactivate them if their role is
  # "Student", but not if their role is "Admin", "CMU Staff", or "Faculty".
  elif "Active" in user['user_status'] and (andrewId not in calculated_andrewIds or not billable):
    # Don't deactivate a whitelisted user.
    if user['whitelisted'] == 'true':
      continue
    if user['user_role'] == 'Student':
      zoho_to_deactivate.add(andrewId)
    else:
      # Take no action to deactivate "Admin", "CMU Staff", or "Faculty" roles,
      # as these are manually reviewed periodically.
      pass

# TODO: Determine whether any preferred names have changed and update Zoho
# records accordingly.

if not args.live:
  # Since there is presently no development environment for Zoho, take no
  # action in DEVELOPMENT mode; rather, simply output the calculated
  # differences.
  logger.info("Environment is %s; NOT adding/removing Zoho users." % environment)
  logger.debug("%d members should be deactivated in Zoho user list...." % len(zoho_to_deactivate))
  for andrewId in sorted(zoho_to_deactivate):
    logger.debug("  %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
  logger.debug("%d members should be activated in Zoho user list...." % len(zoho_to_activate))
  for andrewId in sorted(zoho_to_activate):
    logger.debug("  %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
  logger.debug("%d members should be added to Zoho user list...." % len(zoho_to_add))
  for andrewId in sorted(zoho_to_add):
    logger.debug("  %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
else:
  # In PRODUCTION, add and remove members as determined.
  logger.info("Deactivating %d members in Zoho user list...." % len(zoho_to_deactivate))
  for andrewId in sorted(zoho_to_deactivate):
    try:
      Zoho.deactivate_user(andrewId)
      logger.debug("  Deactivated %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
    except:
      sys.stderr.write("  Zoho error while deactivating member %s!\n" % andrewId)
      logger.error("  Zoho error while deactivating member %s!" % andrewId)
  logger.info("Activating %d members in Zoho user list...." % len(zoho_to_activate))
  for andrewId in sorted(zoho_to_activate):
    try:
      Zoho.activate_user(andrewId)
      logger.debug("  Activated %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
    except:
      sys.stderr.write("  Zoho error while activating member %s!\n" % andrewId)
      logger.error("  Zoho error while activating member %s!" % andrewId)
  logger.info("Adding %d members to Zoho user list...." % len(zoho_to_add))
  for andrewId in sorted(zoho_to_add):
    try:
      Zoho.add_user(andrewId)
      logger.debug("  Added %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
    except:
      sys.stderr.write("  Zoho error while adding member %s!\n" % andrewId)
      logger.error("  Zoho error while adding member %s!" % andrewId)


#   5. Provision access to Stratasys Skylab for 3D printing.
#        - NOTE: Enrollment data is REQUIRED to do this properly, since
#          permissions persist even after a student is no longer
#          contemporaneously enrolled in the course which conferred this
#          privilege.  We accomplish this with the calculated `billable` flag.

# Get a list of existing users.
# NOTE: This will explicitly exclude those with `approver` or `backend`
# permissions so that they are excluded from, and thereby not affected by, this
# calculation.
logger.info("Getting existing users from Skylab....")
skylab_user_data = Skylab.get_users()
skylab_users = {}
existing_andrewIds = set()
for user in skylab_user_data:
  existing_andrewIds.add(user.replace("@andrew.cmu.edu", ""))

calculated_andrewIds = set()
# Start by getting the overriding ACLs for instructor and supplemental access.
groups = [ config.grouper_groups['skylab_instructor_access'], config.grouper_groups['skylab_supplemental_access'] ]
for group in groups:
  logger.info("Getting override ACL group memberships for `%s`...." % group)
  for andrewId in Grouper.get_members(group):
    calculated_andrewIds.add(andrewId)
# Calculate who else should have access based on privileges.
logger.info("Calculating new privilege-based users for Skylab....")
for andrewId in sorted(coalesced_student_privileges.keys()):
  for privilege in [x for x in coalesced_student_privileges[andrewId] if x.key == "3dprint"]:
    # Only maintain the privilege if the user is billable.
    try:
      billable = S3.get_student_from_andrewid(andrewId).billable
    except:
      billable = False
    if privilege.is_current() and billable:
      calculated_andrewIds.add(andrewId)

# Determine differences between current and calculated ACL.
logger.info("Determining user list differences....")
skylab_to_disable = existing_andrewIds.difference(calculated_andrewIds)
skylab_to_enable = calculated_andrewIds.difference(existing_andrewIds)

if not args.live:
  # Since there is presently no development environment for Skylab, take no
  # action in DEVELOPMENT mode; rather, simply output the calculated
  # differences.
  logger.info("Environment is %s; NOT adding/removing Skylab users." % environment)
  logger.debug("%d members should be disabled in Skylab user list...." % len(skylab_to_disable))
  for andrewId in sorted(skylab_to_disable):
    logger.debug("  %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
  logger.debug("%d members should be added/enabled in Skylab user list...." % len(skylab_to_enable))
  for andrewId in sorted(skylab_to_enable):
    logger.debug("  %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
else:
  # In PRODUCTION, add and remove members as determined.
  logger.info("Disabling %d users in Skylab...." % len(skylab_to_disable))
  for andrewId in sorted(skylab_to_disable):
    try:
      Skylab.disable_user(andrewId)
      logger.debug("  Disabled %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
    except Exception as e:
      sys.stderr.write("  Skylab error while adding/enabling member %s: %s\n" % (andrewId, e))
      logger.error("  Skylab error while adding/enabling member %s: %s" % (andrewId, e))
  logger.info("Adding/Enabling %d users to Skylab...." % len(skylab_to_enable))
  for andrewId in sorted(skylab_to_enable):
    try:
      # add_user() here will prefer to enable a previously disabled user, if one exists.
      Skylab.add_user(andrewId)
      logger.debug("  Added/Enabled %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
    except Exception as e:
      sys.stderr.write("  Skylab error while adding/enabling member %s: %s\n" % (andrewId, e))
      logger.error("  Skylab error while adding/enabling member %s: %s" % (andrewId, e))



# We also need TODO the following things:
#   6. TODO: Optionally populate WordPress instances with users tied to
#      rosters. (This is not presently handled by the existing suite of
#      semi-manual scripts.)


# As an additional intermediate output, create stripped-down CSV roster files:
roster_dir = "%s/rosters" % output_dir
roster_file = "rosters-%s.csv" % run_date
roster_path = roster_dir + '/' + roster_file
helpers.mkdir_p(roster_dir)
logger.info("Generating CSV roster at `%s`...." % roster_path)

with open(roster_path, 'w') as csvfile:
  fieldnames = ['SEMESTER ID','COURSE ID','SECTION ID','ANDREW ID','MC LAST NAME','MC FIRST NAME']
  writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
  writer.writeheader()

  for andrewId in sorted(S3.student_sections.keys()):
    for section in S3.student_sections[andrewId]:
      row = {
        'SEMESTER ID': section.semester,
        'COURSE ID': section.course,
        'SECTION ID': section.section,
        'ANDREW ID': andrewId,
        'MC LAST NAME': S3.students[andrewId].lastName,
        'MC FIRST NAME': S3.students[andrewId].commonName
      }
      writer.writerow(row)

csvfile.close()
subprocess.call(["ln", "-sf", roster_file, roster_dir + "/latest-%s.csv" % environment])
if args.live:
  subprocess.call(["ln", "-sf", roster_file, roster_dir + "/latest.csv"])


# Epilogue.
script_end_time = datetime.datetime.now()
logger.info("Done with %s run." % environment)
script_elapsed = (script_end_time - script_begin_time).total_seconds()
logger.info("  Finished: %s" % script_end_time)
logger.info("   Started: %s" % script_begin_time)
logger.info("   Elapsed: %26.6f sec" % script_elapsed)
