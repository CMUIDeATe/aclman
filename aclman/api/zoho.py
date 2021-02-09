import sys
import re
import urllib.request
import urllib.parse
import json

from aclman.models import *
import aclman.api.s3 as S3

secrets = {}

def set_secrets(s):
  global secrets
  secrets = s
  secrets['hostname'] = "https://creator.zoho.com"
  secrets['oauth_host'] = "https://accounts.zoho.com"

  secrets['user_form'] = "New_User_Form"
  secrets['user_view'] = "Users"

def authenticate():
  # Use the (permanent) refresh token to get a (temporary) access token for
  # this run; it will be valid for one hour.
  # https://www.zoho.com/creator/help/api/v2/refresh-the-access-token.html
  endpoint = "%s/oauth/v2/token?client_id=%s&client_secret=%s&refresh_token=%s&grant_type=refresh_token" % (secrets['oauth_host'], secrets['client_id'], secrets['client_secret'], secrets['refresh_token'])
  req = urllib.request.Request(endpoint, data=None, method='POST')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
    if 'error' in resp_data:
      raise Exception("Zoho API error '%s'" % resp_data['error'])
    secrets['oauth_token'] = resp_data['access_token']
    expiration_time = datetime.datetime.now() + datetime.timedelta(seconds=resp_data['expires_in'])
  except urllib.error.HTTPError as e:
    raise e


def get_users():
  global secrets
  user_data = []
  start_num = 0
  page_size = 200
  # Initialize num_received to enter the loop.
  num_received = page_size
  while num_received == page_size:
    get_params = {
      'from': start_num,
      'limit': page_size
    }
    endpoint = "%s/api/v2/%s/%s/report/%s?%s" % (secrets['hostname'], secrets['owner'], secrets['application'], secrets['user_view'], urllib.parse.urlencode(get_params))
    headers = {
      'Authorization': 'Zoho-oauthtoken %s' % secrets['oauth_token']
    }
    req = urllib.request.Request(endpoint, data=None, headers=headers, method='GET')
    try:
      resp = urllib.request.urlopen(req).read()
      resp_data = json.loads(resp.decode('utf-8'))
      num_received = len(resp_data['data'])
      user_data.extend(resp_data['data'])
      start_num += num_received
    except IndexError: # There are no more records.
      break
    except urllib.error.HTTPError as e:
      raise e
  return user_data

def get_user_data(andrewId):
  global secrets
  get_params = {
    'criteria': 'user_aid == "%s"' % andrewId
  }
  endpoint = "%s/api/v2/%s/%s/report/%s?%s" % (secrets['hostname'], secrets['owner'], secrets['application'], secrets['user_view'], urllib.parse.urlencode(get_params))
  headers = {
    'Authorization': 'Zoho-oauthtoken %s' % secrets['oauth_token']
  }
  req = urllib.request.Request(endpoint, data=None, headers=headers, method='GET')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
    return resp_data['data'][0]
  except IndexError:
    raise Exception("Zoho error: No such user '%s'." % andrewId)
  except urllib.error.HTTPError as e:
    raise e

def add_user(andrewId):
  global secrets
  endpoint = "%s/api/v2/%s/%s/form/%s" % (secrets['hostname'], secrets['owner'], secrets['application'], secrets['user_form'])
  student = S3.get_student_from_andrewid(andrewId)
  params = { 'data': {
    'user_aid': andrewId,
    'user_email': "%s@andrew.cmu.edu" % andrewId,
    'user_first': student.commonName,
    'user_last': student.lastName,
    'user_role': "Student",
    'user_status': "Active Enrollment",
    'user_notes': "Added via ACLMAN, %s." % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  } }
  headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Zoho-oauthtoken %s' % secrets['oauth_token']
  }
  req = urllib.request.Request(endpoint, data=json.dumps(params).encode(), headers=headers, method='POST')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
    # NOTE: Zoho validates whether this would create a duplicate and throws an
    # error if so.
    if resp_data['code'] != 3000: # Data Added Successfully
      raise Exception("Zoho error code %d: '%s'" % (resp_data['code'], resp_data['error']))
  except urllib.error.HTTPError as e:
    raise e

def activate_user(andrewId):
  global secrets
  try:
    user_data = get_user_data(andrewId)
  except:
    # If the user doesn't exist, create them instead.
    add_user(andrewId)
    return
  # Don't bother if they're already active.
  if re.search("Active", user_data['user_status']) is not None:
    return
  endpoint = "%s/api/v2/%s/%s/report/%s" % (secrets['hostname'], secrets['owner'], secrets['application'], secrets['user_view'])
  params = {
    'criteria': 'user_aid == "%s"' % andrewId,
    'data': {
      'user_status': "Active Enrollment",
      'user_notes': "%s\nActivated via ACLMAN, %s." % (user_data['user_notes'], datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    }
  }
  headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Zoho-oauthtoken %s' % secrets['oauth_token']
  }
  req = urllib.request.Request(endpoint, data=json.dumps(params).encode(), headers=headers, method='PATCH')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
  except urllib.error.HTTPError as e:
    raise e

def deactivate_user(andrewId):
  global secrets
  try:
    user_data = get_user_data(andrewId)
  except:
    raise Exception("Zoho error: No such user '%s'." % andrewId)
  # Don't bother if they're already inactive.
  if re.search("Inactive", user_data['user_status']) is not None:
    return
  endpoint = "%s/api/v2/%s/%s/report/%s" % (secrets['hostname'], secrets['owner'], secrets['application'], secrets['user_view'])
  params = {
    'criteria': 'user_aid == "%s"' % andrewId,
    'data': {
      'user_status': "Inactive",
      'user_notes': "%s\nDeactivated via ACLMAN, %s." % (user_data['user_notes'], datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    }
  }
  headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Zoho-oauthtoken %s' % secrets['oauth_token']
  }
  req = urllib.request.Request(endpoint, data=json.dumps(params).encode(), headers=headers, method='PATCH')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
  except urllib.error.HTTPError as e:
    raise e
