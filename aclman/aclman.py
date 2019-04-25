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


# Prologue.
script_begin_time = datetime.datetime.now()

cli = CliParser('ACLMAN')
cli.option('--live', dest='live', action='store_true', default=False, help="run ACLMAN live on production systems")
cli.option('-s', '--sectionfile', dest='sectionfile', metavar='FILE', action='store', default="data/sections.csv", help="specify a path to a CSV section file defining privileges")
args = cli.parse()

if args.live:
  import aclman.secrets.production as secrets
  run_date = script_begin_time.strftime("%Y-%m-%d-%H%M%S")
else:
  import aclman.secrets.development as secrets
  run_date = script_begin_time.strftime("%Y-%m-%d-%H%M%S-dryrun")

log_dir = "log"
log_file = "%s.log" % run_date
logging.basicConfig(filename=log_dir + '/' + log_file, format='%(asctime)s.%(msecs)03d:%(levelname)s\t%(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.DEBUG)
subprocess.call(["ln", "-sf", log_file, log_dir + "/latest.log"])

helpers.mkdir_p("output")
logging.info("ACLMAN script started: %s" % script_begin_time)



# Read in and process the list of sections from the section file.
logging.info("Processing requested list of sections from section file `%s`...." % args.sectionfile)

s = open(args.sectionfile, "r")
sreader = csv.reader(s)
all_sections = []
all_section_privileges = {}
for row in sreader:
  # TODO: Be more robust in how this file is read in.
  # TODO: Allow for comments/header in the section file.
  section = Section(row[0], row[1], row[2])

  if section in all_sections:
    logging.debug("Skipping duplicate section %s" % section)
  else:
    # TODO: Verify that the section actually exists by calling
    # `/course/courses?semester=...&courseNumber=...&section=...`
    # NOTE: For now, we catch this later when we try to look up its crosslists.
    all_sections.append(section)
    # Initialize an empty privileges list for this section.
    all_section_privileges[section] = []
    logging.debug("Added section %s" % section)

s.close()


# Read in and process the privileges associated with each section from the
# section file.
logging.info("Processing associated privileges for %d sections from section file `%s`...." % (len(all_sections), args.sectionfile))

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
    logging.debug("Identified new privilege type %s" % privilege_type)
    all_privilege_types.append(privilege_type)
  # Then, register the specific privilege.
  if privilege in all_section_privileges[section]:
    logging.debug("Skipped duplicate privilege for %s: %s" % (section, privilege))
  else:
    all_section_privileges[section].append(privilege)
    logging.debug("Added privilege for %s: %s" % (section, privilege))

s.close()


# Establish auth to S3 API.
s3_api = secrets.s3_api

passman = urllib.request.HTTPPasswordMgrWithDefaultRealm()
passman.add_password(None, s3_api['hostname'], s3_api['username'], s3_api['password'])

authhandler = urllib.request.HTTPBasicAuthHandler(passman)
opener = urllib.request.build_opener(authhandler)
urllib.request.install_opener(opener)


# Find all crosslisted sections, and copy the associated privileges where
# appropriate.
all_crosslisted_sections = []
logging.info("Finding crosslists of the specified sections and copying privileges....")
for section in all_sections:
  section_url = s3_api['hostname'] + '/course/courses/' + str(section)
  try:
    section_response = urllib.request.urlopen(section_url).read()
  except urllib.error.HTTPError:
    sys.stderr.write("Couldn't find crosslists: SECTION %s DOESN'T EXIST!\n" % section)
    logging.error("Couldn't find crosslists: SECTION %s DOESN'T EXIST!" % section)
    # TODO: Also mark `section` as not existing and remove it from the list of
    # sections, in order to avoid making further calls against it.
    continue
  section_data = json.loads(section_response.decode('utf-8'))
  section_crosslists = section_data['crossListedCourses']

  for crosslist in section_crosslists:
    crosslist_section = Section(crosslist['semesterCode'], crosslist['courseNumber'], crosslist['section'])

    if crosslist_section in all_sections:
      # If the section already exists, just skip it.  Don't copy the privileges,
      # as others might be explicitly defined, e.g., different privileges for
      # graduate and undergraduate sections.
      logging.debug("Found %s (crosslist of %s); skipping, already defined" % (crosslist_section, section))
    else:
      logging.debug("Found %s (crosslist of %s); adding new section" % (crosslist_section, section))
      all_crosslisted_sections.append(crosslist_section)
      all_section_privileges[crosslist_section] = []
      # Copy the privileges associated with the original section.
      for privilege in all_section_privileges[section]:
        new_privilege = privilege.replace_sections([crosslist_section])
        all_section_privileges[crosslist_section].append(new_privilege)
        logging.debug("  Copied privilege: %s" % new_privilege)

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
logging.info("Processing rosters for each section....")
all_bio_urls = {}
enrollments_by_bio_url = {}

endpoint = s3_api['hostname'] + '/course/courses/roster'
for section in all_sections:
  parameters = {
    'semester': section.semester,
    'courseNumber': section.course,
    'section': section.section
  }

  # NOTE: Sections which do not exist will still return HTTP 200 with an empty
  # `students` element here.
  section_url = endpoint + '?' + urllib.parse.urlencode(parameters)
  section_response = urllib.request.urlopen(section_url).read()
  section_data = json.loads(section_response.decode('utf-8'))
  section_roster = section_data['students']

  enrollment_count = len(section_roster)
  if enrollment_count == 0:
    logging.warning("%-12s: NO STUDENTS ARE ENROLLED!" % section)
  else:
    logging.debug("%-12s: %2d enrolled" % (section, enrollment_count))

  for enrollment in section_roster:
    # The student BIO URL is a fully-qualified URL.
    bio_url = enrollment['studentURL']

    # Create a record for the student's BIO URL if it hasn't yet been seen.
    if bio_url not in all_bio_urls:
      all_bio_urls[bio_url] = { 'sections': [] }
    # Mark that this student has enrollment in the section being processed.
    # TODO: Fix this data structure so it's useful.
    all_bio_urls[bio_url]['sections'].append(section)


# Get biographical data for each student, and record their sections alongside.
logging.info("Getting biographical data for all %d dedup'd students found...." % len(all_bio_urls))
all_students = {}
all_student_sections = {}

for bio_url in all_bio_urls:
  # Keep track of this student's enrolled sections.
  sections = sorted(all_bio_urls[bio_url]['sections'])

  # NOTE: The `student_response` object should, in principle, contain
  # `finalGrade` data, but doesn't in practice.
  # TODO: Request explicit API access to such `finalGrade` data.
  student_response = urllib.request.urlopen(bio_url).read()
  student_data = json.loads(student_response.decode('utf-8'))
  # TODO: Need to do error-checking on HTTP status.
  student = Student(student_data, bio_url)

  logging.debug("%-8s - %-28s\t%s" % (student.andrewId, student.allNames,
    ','.join(str(x) for x in sections)))

  # Record this student's data and their sections.
  # TODO: Request explicit API access to student enrollment status, e.g., E1,
  # G2, R3, etc.
  all_students[student.andrewId] = student
  all_student_sections[student.andrewId] = sections

# Free the dictionary of BIO URLs since we're done with it.
del all_bio_urls


# Determine each student's privileges.
logging.info("Computing privileges for %d students...." % len(all_students))
all_student_privileges = {}
coalesced_student_privileges = {}

for andrewId in sorted(all_students.keys()):
  student = all_students[andrewId]
  logging.debug("%-8s - %-28s" % (andrewId, student.allNames))
  all_student_privileges[andrewId] = {}

  for section in all_student_sections[andrewId]:
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
      logging.warning("ValueError when attempting to coalesce privileges %s and %s" % (a, b))
      # If for some reason we tried to coalesce unlike privileges, just find
      # any one that is current.
      for privilege in privileges:
        if privilege.is_current():
          coalesced_student_privileges[andrewId].append(privilege)
          logging.warning("  Used %s as the coalesced representative for %s, because it is current" % (privilege, privilege_type))
          break
      # If none are current, take the first.
      coalesced_student_privileges[andrewId].append(privileges[0])
      logging.warning("  Used %s as the coalesced representative for %s, since none were current" % (privileges[0], privilege_type))

  for privilege in coalesced_student_privileges[andrewId]:
    logging.debug("  %s" % privilege)



# Now that we have calculated the set of privileges for each student, generate
# various outputs.



#   1. Generate XML file for door/keycard ACL management, upload via SFTP with
#      SSH keys to the CSGold Util server.
#        - NOTE: Enrollment data is NOT nominaly needed here, as card expiry
#          will override when necessary, but it will help reduce file size and
#          group size.
keycard_dir = "output/keycard"
keycard_file = "keycard-%s.xml" % run_date
keycard_path = keycard_dir + '/' + keycard_file
helpers.mkdir_p(keycard_dir)
logging.info("Generating XML file for CSGold door/keycard ACLs at `%s`...." % keycard_path)

# TODO: Store this mapping in a configuration file.
csgold_group_mapping = {
  'HL A10A': '789',
  'HL A10': '790',
  'HL A5': '791'
}

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
    priv_asgn_group.text = csgold_group_mapping[privilege.value]
    priv_asgn_start.text = str(privilege.start)
    priv_asgn_end.text = str(privilege.end)
    priv_asgn_comment.text = "ACLMAN-%s: %s" % (run_date, ','.join([str(x) for x in privilege.sections]))

# Write out the file.
with open(keycard_path, 'w') as xmlfile:
  xmldata = xml.dom.minidom.parseString(ET.tostring(keycard_xml_root))
  xmlfile.write(xmldata.toprettyxml(indent="  "))
xmlfile.close()
subprocess.call(["ln", "-sf", keycard_file, keycard_dir + "/latest.xml"])

# Upload the file via SFTP to the CSGold Util server.
# NOTE: In Python 3.5, the need for an SFTP batchfile should be avoided by
# reading input from stdin, e.g.,
#   subprocess.run(["sftp", "-b", "-", ...], ..., input=...)
# as opposed to `subprocess.call(...)`.
# See https://docs.python.org/3/library/subprocess.html#subprocess.run
logging.info("Uploading XML file for door/keycard ACLs to CSGold Util server....")
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



# We also need TODO the following things:
#   2. Populate Grouper groups for inclusion in determination of laser cutter
#      access privileges.  (Most users must also appear in EH&S groups
#      indicating completion of Fire Extinguisher Use Training.)
#        - NOTE: Enrollment data is NOT nominaly needed here, as account expiry
#          will override when necessary.
#   3. Generate access lists for room reservation privileges in MRBS; update
#      via direct entries into the MySQL database.
#        - NOTE: Enrollment data is NOT nominaly needed here, as this privilege
#          is only granted for the current semester for HL A10A only.
#   4. Compare with a dump of existing user lists from Zoho/Quartermaster for
#      Lending Desk privileges, determine diffs, and output them to a place
#      where they can be manually processed in Zoho.  (Zoho cannot pull
#      external data.)
#        - NOTE: Enrollment data is REQUIRED to do this properly, since
#          permissions persist even after a student is no longer
#          contemporaneously enrolled in the course which conferred this
#          privilege.
#   5. TODO: Optionally populate WordPress instances with users tied to
#      rosters. (This is not presently handled by the existing suite of
#      semi-manual scripts.)


# In the meantime, as an intermediate output, create stripped-down CSV roster
# files:
roster_dir = "output/rosters"
roster_file = "rosters-%s.csv" % run_date
roster_path = roster_dir + '/' + roster_file
helpers.mkdir_p(roster_dir)
logging.info("Generating CSV roster at `%s`...." % roster_path)

with open(roster_path, 'w') as csvfile:
  fieldnames = ['SEMESTER ID','COURSE ID','SECTION ID','ANDREW ID','MC LAST NAME','MC FIRST NAME']
  writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
  writer.writeheader()

  for andrewId in sorted(all_student_sections.keys()):
    for section in all_student_sections[andrewId]:
      row = {
        'SEMESTER ID': section.semester,
        'COURSE ID': section.course,
        'SECTION ID': section.section,
        'ANDREW ID': andrewId,
        'MC LAST NAME': all_students[andrewId].lastName,
        'MC FIRST NAME': all_students[andrewId].commonName
      }
      writer.writerow(row)

csvfile.close()
subprocess.call(["ln", "-sf", roster_file, roster_dir + "/latest.csv"])


# Epilogue.
script_end_time = datetime.datetime.now()
logging.info("Done.")
script_elapsed = (script_end_time - script_begin_time).total_seconds()
logging.info("  Finished: %s" % script_end_time)
logging.info("   Started: %s" % script_begin_time)
logging.info("   Elapsed: %26.6f sec" % script_elapsed)
