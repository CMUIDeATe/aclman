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

def get_roster_bio_urls(section):
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

def get_student_from_bio_url(bio_url):
  global secrets
  endpoint = bio_url
  student_response = urllib.request.urlopen(endpoint).read()
  student_data = json.loads(student_response.decode('utf-8'))
  # TODO: Need to do error-checking on HTTP status.
  student = Student(student_data, bio_url)
  return student
