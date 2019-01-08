#!/usr/bin/python3

import datetime
import logging
import subprocess
import csv, json
import urllib.request
import urllib.parse

from models import *
import config.secrets as secrets


# Prologue.
script_begin_time = datetime.datetime.now()

run_date = script_begin_time.strftime("%Y-%m-%d-%H%M%S")
log_dir = "log"
log_file = "%s.log" % run_date
logging.basicConfig(filename=log_dir + '/' + log_file, format='%(asctime)s.%(msecs)03d:%(levelname)s\t%(message)s', datefmt='%Y-%m-%d %H:%M:%S', level=logging.DEBUG)
subprocess.call(["ln", "-sf", log_file, log_dir + "/latest.log"])

logging.info("ACLMAN script started: %s" % script_begin_time)



# Read in and process the list of sections.
logging.info("Processing list of sections....")

# TODO: Allow for other section files to be read in.
s = open("data/sections.csv", "r")
sreader = csv.reader(s)
all_sections = []
for row in sreader:
  # TODO: Be more robust in how this file is read in.
  section = Section(row[0], row[1], row[2])
  if section in all_sections:
    logging.debug("Skipping duplicate section %s" % section)
  else:
    all_sections.append(section)
    logging.debug("Added section %s" % section)
# TODO: Anything regarding loading in privileges associated with each section.


# Establish auth to S3 API.
s3_api = secrets.s3_api

passman = urllib.request.HTTPPasswordMgrWithDefaultRealm()
passman.add_password(None, s3_api['hostname'], s3_api['username'], s3_api['password'])

authhandler = urllib.request.HTTPBasicAuthHandler(passman)
opener = urllib.request.build_opener(authhandler)
urllib.request.install_opener(opener)


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

  section_url = endpoint + '?' + urllib.parse.urlencode(parameters)
  section_response = urllib.request.urlopen(section_url).read()
  section_data = json.loads(section_response.decode('utf-8'))
  section_roster = section_data['students']

  # TODO: Need to do error-checking on HTTP status.
  enrollment_count = len(section_roster)
  if enrollment_count == 0:
    logging.warning("%s: NO STUDENTS ARE ENROLLED!" % section)
  else:
    logging.info("%s: %2d enrolled" % (section, enrollment_count))

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

  # Record this student's data and their sections together.
  # TODO: Request explicit API access to student enrollment status, e.g., E1,
  # G2, R3, etc.
  all_students[student.andrewId] = { 'data': student, 'sections': sections }

# Free the dictionary of BIO URLs since we're done with it.
del all_bio_urls


# Once we have the data for all relevant courses, combine with list of section
# priviliges TODO the following things:
#   1. Generate XML file for door/keycard ACL management, upload via SFTP with
#      SSH keys to the CSGold Util server.
#        - TODO: Improve existing codebase to use actual diffs for both add and
#          drop.
#        - TODO: Before uploading new ACL file, compare with previous and log
#          diffs.  This will make the reasons for drops easier to determine
#          empirically.
#   2. Populate Grouper groups for inclusion in determination of laser cutter
#      access privileges.  (Most users must also appear in EH&S groups
#      indicating completion of Fire Extinguisher Use Training.)
#   3. Generate access lists for room reservation privileges in MRBS; update
#      via direct entries into the MySQL database.
#   4. Compare with a dump of existing user lists from Zoho/Quartermaster for
#      Lending Desk privileges, determine diffs, and output them to a place
#      where they can be manually processed in Zoho.  (Zoho cannot pull
#      external data.)
#   5. TODO: Optionally populate WordPress instances with users tied to
#      rosters. (This is not presently handled by the existing suite of
#      semi-manual scripts.)


# Epilogue.
script_end_time = datetime.datetime.now()
logging.info("Done.")
script_elapsed = (script_end_time - script_begin_time).total_seconds()
logging.info("  Finished: %s" % script_end_time)
logging.info("   Started: %s" % script_begin_time)
logging.info("   Elapsed: %26.6f sec" % script_elapsed)
