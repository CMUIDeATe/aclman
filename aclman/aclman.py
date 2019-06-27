#!/usr/bin/python3

import datetime
import logging
import sys
import subprocess
import csv, json
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


# Prologue.
script_begin_time = datetime.datetime.now()

cli = CliParser('ACLMAN')
cli.option('--live', dest='live', action='store_true', default=False, help="run ACLMAN live on production systems")
cli.option('-s', '--sectionfile', dest='sectionfile', metavar='FILE', action='store', default="data/sections.csv", help="specify a path to a CSV section file defining privileges")
args = cli.parse()

if args.live:
  import aclman.config.production as config
  import aclman.secrets.production as secrets
  run_date = script_begin_time.strftime("%Y-%m-%d-%H%M%S")
  environment = "PRODUCTION"
else:
  # Confirm development runs before beginning, especially since inputs can be large.
  response = input("Begin a DEVELOPMENT run on `%s`? (y/n) " % args.sectionfile)
  if response.lower() not in ['y', 'yes']:
    print("Aborted.")
    sys.exit(1)
  import aclman.config.development as config
  import aclman.secrets.development as secrets
  run_date = script_begin_time.strftime("%Y-%m-%d-%H%M%S-dryrun")
  environment = "DEVELOPMENT"

# Establish auth to each API.
S3.set_secrets(secrets.s3_api)
Grouper.set_secrets(secrets.grouper_api)
Mrbs.set_secrets(secrets.mrbs_db)

# Configure logging.
log_dir = "log"
log_file = "%s.log" % run_date

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

helpers.mkdir_p("output")
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
# into the `all_bio_urls` structure, which abstracts each student to their BIO
# URL.
#
# NOTE: We maintain this layer of abstraction for now because getting actual
# data on the students themselves requires a separate API call, which we
# minimize here by coalescing records with the same student BIO URL before
# moving on.
logger.info("Processing rosters for each section....")
all_bio_urls = {}
enrollments_by_bio_url = {}

for section in all_sections:
  section_roster = S3.get_roster_bio_urls(section)
  enrollment_count = len(section_roster)
  if enrollment_count == 0:
    logger.warning("%-12s: NO STUDENTS ARE ENROLLED!" % section)
  else:
    logger.debug("%-12s: %2d enrolled" % (section, enrollment_count))

  for enrollment in section_roster:
    # The student BIO URL is a fully-qualified URL.
    bio_url = enrollment['studentURL']

    # Create a record for the student's BIO URL if it hasn't yet been seen.
    if bio_url not in all_bio_urls:
      all_bio_urls[bio_url] = { 'sections': [] }
    # Mark that this student has enrollment in the section being processed.
    # TODO: Fix this data structure so it's useful.
    all_bio_urls[bio_url]['sections'].append(section)

    # NOTE: The `section_roster` object should, in principle, contain
    # `finalGrade` data for each student, but doesn't in practice.
    # TODO: Request explicit API access to such `finalGrade` data.


# Get biographical data for each student, and record their sections alongside.
logger.info("Getting biographical data for all %d dedup'd students found...." % len(all_bio_urls))
for bio_url in all_bio_urls:
  # Keep track of this student's enrolled sections.
  sections = sorted(all_bio_urls[bio_url]['sections'])
  student = S3.get_student_from_bio_url(bio_url)

  logger.debug("%-8s - %-28s\t%s" % (student.andrewId, student.allNames,
    ','.join(str(x) for x in sections)))

  # Record this student's data and their sections.
  # TODO: Request explicit API access to student enrollment status, e.g., E1,
  # G2, R3, etc.
  S3.students[student.andrewId] = student
  S3.student_sections[student.andrewId] = sections

# Free the dictionary of BIO URLs since we're done with it.
del all_bio_urls


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
jsondata_dir = "output/jsondata"
jsondata_file = "data-%s.json" % run_date
jsondata_path = jsondata_dir + '/' + jsondata_file
helpers.mkdir_p(jsondata_dir)
logger.info("Generating JSON file to locally cache calculated data at `%s`...." % jsondata_path)

all_data = {}
for student in S3.students:
  all_data[student] = {'biographical': S3.students[student], 'sections': S3.student_sections[student], 'privileges': coalesced_student_privileges[student]}

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
keycard_dir = "output/keycard"
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

# TODO: Compare the just-generated ACL file with the previous version and log
# the diffs locally.  This will make the reasons for drops easier to determine
# empirically.


#   2. Populate Grouper groups for inclusion in determination of laser cutter
#      access privileges.  (Most users must also appear in EH&S groups
#      indicating completion of their "Fire Extinguisher Training" and "Laser
#      Cutter Safety" modules.)
#        - NOTE: Enrollment data is NOT nominaly needed here, as account expiry
#          will override when necessary.
laser_group = config.grouper_groups['laser_course']

# Get the existing group members.
logger.info("Getting existing group memberships for `%s`...." % laser_group)
existing_andrewIds = Grouper.get_members(laser_group)

# Calculate who should be in the group based on privileges.
logger.info("Calculating new group memberships for `%s`...." % laser_group)
calculated_andrewIds = set()
for andrewId in sorted(coalesced_student_privileges.keys()):
  for privilege in [x for x in coalesced_student_privileges[andrewId] if x.key == "laser_course"]:
    if privilege.is_current():
      calculated_andrewIds.add(andrewId)

# Determine differences between current and calculated group membership.
logger.info("Determining group membership differences....")
grouper_to_del = existing_andrewIds.difference(calculated_andrewIds)
grouper_to_add = calculated_andrewIds.difference(existing_andrewIds)

# Add and remove members as determined.
logger.info("Removing %d members from group `%s`...." % (len(grouper_to_del), laser_group))
for andrewId in sorted(grouper_to_del):
  try:
    Grouper.remove_member(laser_group, andrewId)
    logger.debug("  Removed %s", S3.students[andrewId] if andrewId in S3.students else andrewId)
  except urllib.error.HTTPError as e:
    sys.stderr.write("  Grouper error while removing member %s: %s\n" % (andrewId, e))
    logger.error("  Grouper error while removing member %s: %s" % (andrewId, e))
logger.info("Adding %d members to group `%s`...." % (len(grouper_to_add), laser_group))
for andrewId in sorted(grouper_to_add):
  try:
    Grouper.add_member(laser_group, andrewId)
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



# We also need TODO the following things:
#   4. Compare with a dump of existing user lists from Zoho/Quartermaster for
#      Lending Desk privileges, determine diffs, and update Zoho memberships
#      accordingly.
#        - NOTE: Enrollment data is REQUIRED to do this properly, since
#          permissions persist even after a student is no longer
#          contemporaneously enrolled in the course which conferred this
#          privilege.
#   5. TODO: Optionally populate WordPress instances with users tied to
#      rosters. (This is not presently handled by the existing suite of
#      semi-manual scripts.)


# As an additional intermediate output, create stripped-down CSV roster files:
roster_dir = "output/rosters"
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
