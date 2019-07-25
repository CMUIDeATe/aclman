import sys
import urllib.request
import urllib.parse
import json

from aclman.models import *

secrets = {}

students = {}
student_sections = {}

def set_secrets(s):
  global secrets
  secrets = s

  passman = urllib.request.HTTPPasswordMgrWithDefaultRealm()
  passman.add_password(None, secrets['hostname'], secrets['username'], secrets['password'])

  authhandler = urllib.request.HTTPBasicAuthHandler(passman)
  opener = urllib.request.build_opener(authhandler)
  urllib.request.install_opener(opener)


def get_crosslists(section):
  global secrets
  endpoint = "%s/course/courses/%s" % (secrets['hostname'], str(section))
  try:
    resp = urllib.request.urlopen(endpoint).read()
    section_data = json.loads(resp.decode('utf-8'))
    section_crosslists = section_data['crossListedCourses']
  except urllib.error.HTTPError as e:
    sys.stderr.write("Couldn't find crosslists: SECTION %s DOESN'T EXIST!\n" % section)
    section_crosslists = []
  return [ Section(crosslist['semesterCode'], crosslist['courseNumber'], crosslist['section']) for crosslist in section_crosslists ]

def get_roster_bioUrls(section):
  global secrets
  parameters = {
    'semester': section.semester,
    'courseNumber': section.course,
    'section': section.section
  }
  endpoint = "%s/course/courses/roster?%s" % (secrets['hostname'], urllib.parse.urlencode(parameters))
  # NOTE: Sections which do not exist will still return HTTP 200 with an empty
  # `students` element here.
  section_response = urllib.request.urlopen(endpoint).read()
  section_data = json.loads(section_response.decode('utf-8'))
  section_roster = section_data['students']
  return section_roster


def get_student_from_andrewid(andrewId):
  global students
  # Return memoized copy, if available.
  if andrewId in students:
    return students[andrewId]
  # Otherwise, fetch the student's data from S3.
  __fetch_student_data_from_andrewid(andrewId)
  # NOTE: When fetching students in this fashion, `bioID` will come back null.
  # Access to this data can be requested if it is needed.
  return students[andrewId]

def get_student_from_bioid(bioId):
  global students
  andrewId = __translate_bioid_to_andrewid(bioId)
  get_student_from_andrewid(andrewId)
  # Fill in the missing `bioID` value, since it is known.
  students[andrewId].set_bioId(bioId)
  return students[andrewId]

def __translate_bioid_to_andrewid(bioId):
  # NOTE: This could also be memoized.
  global secrets
  endpoint = "%s/student/bio/%s?idType=BIO" % (secrets['hostname'], bioId)
  bio_response = urllib.request.urlopen(endpoint).read()
  try:
    bio_data = json.loads(bio_response.decode('utf-8'))
  except:
    # HTTP 200 with blank response implies that no student record exists.
    return None
  return bio_data['andrewId']

def __fetch_student_data_from_andrewid(andrewId):
  global secrets, students
  data = {}
  # Get biographical data.
  endpoint = "%s/student/bio/%s?idType=ANDREW" % (secrets['hostname'], andrewId)
  bio_response = urllib.request.urlopen(endpoint).read()
  try:
    bio_data = json.loads(bio_response.decode('utf-8'))
    data['biographical'] = {
      'andrewId': bio_data['andrewId'],
      'bioId': bio_data['bioId'],
      'cardId': bio_data['cardId'],
      'firstName': bio_data['firstName'],
      'lastName': bio_data['lastName'],
      'preferredName': bio_data['preferredName']
    }
  except:
    # HTTP 200 with blank response implies that no student record exists.
    return None
  # Persist the data for this student to the global cache before returning it.
  students[andrewId] = Student(data)
  return students[andrewId]
