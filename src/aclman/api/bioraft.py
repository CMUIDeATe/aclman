import functools
import urllib.request
import json

from datetime import datetime, timedelta
import jwt

from .. import config_handler
from .. import helpers

secrets = None
training_courses = None


def load_secrets():
  global secrets
  secrets = config_handler.get_secrets('bioraft_api')
  authenticate()

def authenticate():
  if secrets is None:
    load_secrets()

  now = helpers.now()
  payload = {
    'iat': now - timedelta(minutes=5),
    'exp': now + timedelta(hours=1),
    'drupal': { 'uid': secrets['user_id'] }
  }
  with open(secrets['ssh_key_path'], 'rb') as fh:
    rsa_key = fh.read()

  encoded = jwt.encode(payload, rsa_key, algorithm='RS256', headers={ 'kid': secrets['key_id'] } )
  secrets['jwt_token'] = encoded

def load_training_courses():
  global training_courses
  training_courses = config_handler.get_config('bioraft_training_courses')


def get_course_training_records(course_id, training_days):
  if secrets is None:
    load_secrets()

  get_params = {
    'filter[status]': 1,
    'filter[course][condition][path]': 'course_id.drupal_internal__nid',
    'filter[course][condition][operator]': '=',
    'filter[course][condition][value]': course_id,
    'filter[creAft][condition][path]': 'created',
    'filter[creAft][condition][operator]': '>=',
    'filter[creAft][condition][value]': (datetime.utcnow() - timedelta(days=training_days)).timestamp(),
    'page[offset]': 0,
    'page[limit]': 50
  }
  endpoint = "%s/jsonapi/raft_training_record/raft_training_record?%s" % (secrets['hostname'], urllib.parse.urlencode(get_params))
  headers = {
    'Authorization': 'UsersJwt %s' % secrets['jwt_token']
  }

  while True:
    req = urllib.request.Request(endpoint, headers=headers, method='GET')
    try:
      resp = urllib.request.urlopen(req).read()
      resp_data = json.loads(resp.decode('utf-8'))
      for entry in resp_data['data']:
        yield entry
      # Get next endpoint URL
      endpoint = resp_data['links']['next']['href']
    except KeyError:  # no next endpoint
      return
    except urllib.error.HTTPError as e:
      raise Exception("BioRAFT error %s" % (e))

def get_recent_trainings(course_id, training_days):
  for entry in get_course_training_records(course_id, training_days):
    user_uuid = entry['relationships']['user_id']['data']['id']
    created = entry['attributes']['created']
    andrewId = translate_user_uuid_to_andrewid(user_uuid)
    yield ( andrewId, created )

@functools.cache
def translate_user_uuid_to_andrewid(user_id):
  if secrets is None:
    load_secrets()

  endpoint = "%s/jsonapi/user/user/%s" % (secrets['hostname'], user_id)
  headers = {
    'Authorization': 'UsersJwt %s' % secrets['jwt_token']
  }
  req = urllib.request.Request(endpoint, headers=headers, method='GET')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
    return resp_data['data']['attributes']['mail'].replace("@andrew.cmu.edu","")
  except urllib.error.HTTPError as e:
    raise Exception("BioRAFT error %s" % (e))

@functools.cache
def translate_andrewid_to_user_uuid(andrewId):
  if secrets is None:
    load_secrets()

  get_params = {
    'filter[status]': 1,
    'filter[mail][condition][path]': 'mail',
    'filter[mail][condition][operator]': '=',
    'filter[mail][condition][value]': '%s@andrew.cmu.edu' % andrewId,
  }
  endpoint = "%s/jsonapi/user/user?%s" % (secrets['hostname'], urllib.parse.urlencode(get_params))
  headers = {
    'Authorization': 'UsersJwt %s' % secrets['jwt_token']
  }
  req = urllib.request.Request(endpoint, headers=headers, method='GET')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
    return resp_data['data'][0]['id']   # User UUID
  except IndexError:
    raise Exception("No such user %s" % (andrewId))
  except urllib.error.HTTPError as e:
    raise Exception("BioRAFT error %s" % (e))

@functools.cache
def translate_andrewid_to_user_id_number(andrewId):
  if secrets is None:
    load_secrets()

  get_params = {
    'filter[status]': 1,
    'filter[mail][condition][path]': 'mail',
    'filter[mail][condition][operator]': '=',
    'filter[mail][condition][value]': '%s@andrew.cmu.edu' % andrewId,
  }
  endpoint = "%s/jsonapi/user/user?%s" % (secrets['hostname'], urllib.parse.urlencode(get_params))
  headers = {
    'Authorization': 'UsersJwt %s' % secrets['jwt_token']
  }
  req = urllib.request.Request(endpoint, headers=headers, method='GET')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
    return resp_data['data'][0]['attributes']['drupal_internal__uid']   # User ID number
  except IndexError:
    raise Exception("No such user %s" % (andrewId))
  except urllib.error.HTTPError as e:
    raise Exception("BioRAFT error %s" % (e))

# Get a selected training record for a user.
def get_user_training_record(andrewId, course_id):
  if secrets is None:
    load_secrets()

  try:
    user_uuid = translate_andrewid_to_user_uuid(andrewId)
  except:
    return {}

  get_params = {
    'filter[status]': 1,
    'filter[course][condition][path]': 'course_id.drupal_internal__nid',
    'filter[course][condition][operator]': '=',
    'filter[course][condition][value]': course_id,
    'filter[user][condition][path]': 'user_id.id',
    'filter[user][condition][operator]': '=',
    'filter[user][condition][value]': user_uuid
  }
  endpoint = "%s/jsonapi/raft_training_record/raft_training_record?%s" % (secrets['hostname'], urllib.parse.urlencode(get_params))
  headers = {
    'Authorization': 'UsersJwt %s' % secrets['jwt_token']
  }

  req = urllib.request.Request(endpoint, headers=headers, method='GET')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
    # NOTE: There can be more than one entry.
    entry = resp_data['data'][0]
  except IndexError:
    return {}
  try:
    completed_timestamp = helpers.iso_to_local(entry['attributes']['created'])
    user_training = {
        'title': get_course_title(course_id),
        'completed': completed_timestamp
    }
    return user_training
  except urllib.error.HTTPError as e:
    raise Exception("BioRAFT error %s" % (e))

# Get training records for a user from a list of selected courses.
def get_user_trainings(andrewId, course_ids):
  try:
    user_trainings = {}
    for course_id in course_ids:
      user_trainings[course_id] = get_user_training_record(andrewId, course_id)
    return user_trainings
  except urllib.error.HTTPError as e:
    raise Exception("BioRAFT error %s" % (e))

# Get ALL training records present in the entire BioRAFT system for a user.
def get_all_user_trainings(andrewId):
  if secrets is None:
    load_secrets()

  try:
    user_uuid = translate_andrewid_to_user_uuid(andrewId)
    user_id_number = translate_andrewid_to_user_id_number(andrewId)
  except:
    return {}

  get_params = {
    'filter[status]': 1,
    'filter[user][condition][path]': 'user_id.id',
    'filter[user][condition][operator]': '=',
    'filter[user][condition][value]': user_uuid
  }
  endpoint = "%s/jsonapi/raft_training_record/raft_training_record?%s" % (secrets['hostname'], urllib.parse.urlencode(get_params))
  headers = {
    'Authorization': 'UsersJwt %s' % secrets['jwt_token']
  }

  req = urllib.request.Request(endpoint, headers=headers, method='GET')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
    user_trainings = {}
    for entry in resp_data['data']:
      course_id = entry['relationships']['course_id']['data']['meta']['drupal_internal__target_id']
      completed_time = entry['attributes']['created']
      completed_timestamp = helpers.iso_to_local(completed_time)
      user_trainings[course_id] = {
        'title': get_course_title(course_id),
        'completed': completed_timestamp,
	# Construct a URL to access the associated PDF certificate when
	# authenticated to BioRAFT.
        'certificate_url': "https://cmu.bioraft.com/raft/training/trainingRecords/cert/%s/%s/%s" % (course_id, user_id_number, helpers.iso_to_posix(completed_time))
      }
    return user_trainings
  except urllib.error.HTTPError as e:
    raise Exception("BioRAFT error %s" % (e))

def get_all_user_trainings_tiered(andrewId):
  if training_courses is None:
    load_training_courses()
  all_trainings = get_all_user_trainings(andrewId)

  primary_trainings = { course_id: all_trainings[course_id] for course_id in training_courses if 'primary' in training_courses[course_id] and training_courses[course_id]['primary'] }
  other_trainings = { course_id: record for course_id, record in all_trainings.items() if course_id not in primary_trainings }

  return {
    'primary_trainings': primary_trainings,
    'other_trainings': other_trainings
  }

def get_course_title(course_id):
  if secrets is None:
    load_secrets()
  if training_courses is None:
    load_training_courses()

  get_params = {
    'filter[status]': 1,
    'filter[drupal_internal__nid][condition][path]': 'drupal_internal__nid',
    'filter[drupal_internal__nid][condition][operator]': '=',
    'filter[drupal_internal__nid][condition][value]': course_id
  }
  endpoint = "%s/jsonapi/node/raft_training_course?%s" % (secrets['hostname'], urllib.parse.urlencode(get_params))
  headers = {
    'Authorization': 'UsersJwt %s' % secrets['jwt_token']
  }

  req = urllib.request.Request(endpoint, headers=headers, method='GET')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
  except urllib.error.HTTPError as e:
    raise Exception("BioRAFT error %s" % (e))
  try:
    data = resp_data['data'].pop()
    return data['attributes']['title']
  except IndexError:
    # Unknown or deprecated training courses will result in an IndexError, so
    # fall back to a default name for the training course unless it's one of
    # the ones we know.
    if course_id in training_courses:
      return "[DEPRECATED] %s" % training_courses[course_id]['title']
    return "[DEPRECATED] Unknown training %d" % course_id
