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

  secrets['user_form'] = "ADD_User"
  secrets['user_view'] = "USER_INFO"


def get_users():
  global secrets
  endpoint = "%s/api/json/%s/view/%s" % (secrets['hostname'], secrets['application'], secrets['user_view'])
  params = {
    'authtoken': secrets['authtoken'],
    'scope': "creatorapi",
    'raw': "true"
  }
  req = urllib.request.Request(endpoint, data=urllib.parse.urlencode(params).encode(), method='POST')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
    return resp_data
  except urllib.error.HTTPError as e:
    raise e

def get_user_data(andrewId):
  global secrets
  endpoint = "%s/api/json/%s/view/%s" % (secrets['hostname'], secrets['application'], secrets['user_view'])
  params = {
    'authtoken': secrets['authtoken'],
    'scope': "creatorapi",
    'raw': "true",
    'criteria': 'user_aid == "%s"' % andrewId
  }
  req = urllib.request.Request(endpoint, data=urllib.parse.urlencode(params).encode(), method='POST')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
    return resp_data[secrets['user_form']][0]
  except IndexError:
    raise Exception("Zoho error: No such user '%s'." % andrewId)
  except urllib.error.HTTPError as e:
    raise e

def add_user(andrewId):
  global secrets
  endpoint = "%s/api/%s/json/%s/form/%s/record/add" % (secrets['hostname'], secrets['owner'], secrets['application'], secrets['user_form'])
  student = S3.get_student(andrewId)
  params = {
    'authtoken': secrets['authtoken'],
    'scope': "creatorapi",
    'user_aid': andrewId,
    'user_email': "%s@andrew.cmu.edu" % andrewId,
    'user_first': student.commonName,
    'user_last': student.lastName,
    'user_role': "Student",
    'user_status': "Active Enrollment",
    'user_notes': "Added via ACLMAN, %s." % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  }
  req = urllib.request.Request(endpoint, data=urllib.parse.urlencode(params).encode(), method='POST')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
    # NOTE: Zoho validates whether this would create a duplicate and throws
    # an error if so.
    resp_status = resp_data['formname'][1]['operation'][1]['status']
    if resp_status != "Success":
      raise Exception("Zoho error: %s" % resp_status)
  except urllib.error.HTTPError as e:
    raise e

def activate_user(andrewId):
  global secrets
  try:
    user_data = get_user_data(andrewId)
  except:
    # TODO: If the user doesn't exist, create them instead.
    return
  # Don't bother if they're already active.
  if re.search("Active", user_data['user_status']) is not None:
    return
  endpoint = "%s/api/%s/json/%s/form/%s/record/update" % (secrets['hostname'], secrets['owner'], secrets['application'], secrets['user_form'])
  params = {
    'authtoken': secrets['authtoken'],
    'scope': "creatorapi",
    'criteria': 'user_aid == "%s"' % andrewId,
    'user_status': "Active Enrollment",
    'user_notes': "%s\nActivated via ACLMAN, %s." % (user_data['user_notes'], datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
  }
  req = urllib.request.Request(endpoint, data=urllib.parse.urlencode(params).encode(), method='POST')
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
  endpoint = "%s/api/%s/json/%s/form/%s/record/update" % (secrets['hostname'], secrets['owner'], secrets['application'], secrets['user_form'])
  params = {
    'authtoken': secrets['authtoken'],
    'scope': "creatorapi",
    'criteria': 'user_aid == "%s"' % andrewId,
    'user_status': "Inactive",
    'user_notes': "%s\nDeactivated via ACLMAN, %s." % (user_data['user_notes'], datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
  }
  req = urllib.request.Request(endpoint, data=urllib.parse.urlencode(params).encode(), method='POST')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
  except urllib.error.HTTPError as e:
    raise e
