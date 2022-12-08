import sys
import urllib.request
import urllib.parse
import json

from aclman.models import *
import aclman.helpers as helpers

secrets = {}

students = {}
student_sections = {}

business_semester = helpers.business_semester()
opener = urllib.request.build_opener(urllib.request.BaseHandler()) # default opener

def set_secrets(s):
  global secrets, opener
  secrets = s

  passman = urllib.request.HTTPPasswordMgrWithDefaultRealm()
  passman.add_password(None, secrets['hostname'], secrets['username'], secrets['password'])

  authhandler = urllib.request.HTTPBasicAuthHandler(passman)
  opener = urllib.request.build_opener(authhandler)


def get_crosslists(section):
  global secrets, opener
  endpoint = "%s/course/courses/%s" % (secrets['hostname'], str(section))
  try:
    resp = opener.open(endpoint).read()
    section_data = json.loads(resp.decode('utf-8'))
    section_crosslists = section_data['crossListedCourses']
  except urllib.error.HTTPError as e:
    sys.stderr.write("Couldn't find crosslists: SECTION %s DOESN'T EXIST!\n" % section)
    section_crosslists = []
  return [ Section(crosslist['semesterCode'], crosslist['courseNumber'], crosslist['section']) for crosslist in section_crosslists ]

def get_roster_bioUrls(section):
  global secrets, opener
  parameters = {
    'semester': section.semester,
    'courseNumber': section.course,
    'section': section.section
  }
  endpoint = "%s/course/courses/roster?%s" % (secrets['hostname'], urllib.parse.urlencode(parameters))
  # NOTE: Sections which do not exist will still return HTTP 200 with an empty
  # `students` element here.
  section_response = opener.open(endpoint).read()
  section_data = json.loads(section_response.decode('utf-8'))
  section_roster = section_data['students']
  return section_roster


def is_billable(andrewId):
  try:
    billable = get_student_from_andrewid(andrewId).billable
  except:
    billable = False
  return billable

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
  global secrets, opener
  endpoint = "%s/student/bio/%s?idType=BIO" % (secrets['hostname'], bioId)
  bio_response = opener.open(endpoint).read()
  try:
    bio_data = json.loads(bio_response.decode('utf-8'))
  except:
    # HTTP 200 with blank response implies that no student record exists.
    return None
  return bio_data['andrewId']

def __fetch_student_data_from_andrewid(andrewId):
  global secrets, opener, students, business_semester
  data = {}

  # Get biographical data for the student.
  endpoint = "%s/student/bio/%s?idType=ANDREW" % (secrets['hostname'], andrewId)
  bio_response = opener.open(endpoint).read()
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

  # Get academic data for the student for the current business semester.  If
  # it's summer, query both sessions (M and N) as well as the following fall.
  data['academic'] = {}
  billable = False
  if business_semester.sem_type == 'U':
    year_code = business_semester.year_code
    query_semesters = [Semester('M%s' % year_code), Semester('N%s' % year_code), Semester('F%s' % year_code)]
  else:
    query_semesters = [business_semester]
  # NOTE: The `enrollmentStatusFlag` provided by the API is 'Y' if the
  # student's enrollment status code is any of:
  # - E1: Enrolled
  # - R1: Conditionally Enrolled
  # - R3: Eligible to Enroll
  for semester in query_semesters:
    endpoint = "%s/student/academic/%s?idType=ANDREW&semesterCode=%s" % (secrets['hostname'], andrewId, semester)
    academic_response = opener.open(endpoint).read()
    try:
      academic_data = json.loads(academic_response.decode('utf-8'))
      data['academic'][str(semester)] = {
        'enrolled': (academic_data['enrollmentStatusFlag'] == 'Y'),
        'graduationSemester': academic_data['graduationSemesterCode']
      }
    except:
      # HTTP 200 with blank response implies that a student record exists, but
      # has no academic record for the specified semester.
      data['academic'][str(semester)] = {
        'enrolled': False,
        'graduationSemester': None
      }
    # A student is considered billable if they are enrolled in any of the
    # `query_semesters`.
    billable = billable or data['academic'][str(semester)]['enrolled']
  data['academic']['billable'] = billable
  # A student is considered a pending graduate, for our purposes, if the most
  # recent/current graduation semester code is equivalent to the current
  # semester.
  grad_semester = data['academic'][str(query_semesters[-1])]['graduationSemester']
  if grad_semester is None:
    data['academic']['pendingGraduate'] = False
  else:
    data['academic']['pendingGraduate'] = ( Semester(grad_semester) == business_semester )

  # Persist the data for this student to the global cache before returning it.
  students[andrewId] = Student(data)
  return students[andrewId]
