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
  secrets['hostname'] = "https://skylabapi.zombiesoft.net"


def get_users():
  global secrets
  # Use the `approver` and `backend` filters to only get regular users without
  # administrative permissions.  Use the `enabled` and `deleted` filters to
  # only get those remaining who have active accounts on Skylab.
  search_parameters = {
    'search': '@',
    'enabled': 'true',
    'deleted': 'false',
    'approver': 'false',
    'backend': 'false'
  }
  return __search_users(search_parameters)

def get_user_data(andrewId):
  global secrets
  parameters = {
    'eppn': "%s@andrew.cmu.edu" % andrewId
  }
  endpoint = "%s/api/entities/academics-list?%s" % (secrets['hostname'], urllib.parse.urlencode(parameters))
  headers = {
    'Content-Type': 'application/json',
    'api_key': secrets['api_key']
  }
  req = urllib.request.Request(endpoint, data=json.dumps(parameters).encode(), headers=headers, method='GET')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
    return resp_data['payload'][0]
  except urllib.error.HTTPError as e:
    raise Exception("Skylab error %s: %s\n%s" % (error['errorCode'], error['errorMsg'], error['errorDetails']))

def add_user(andrewId):
  # This endpoint will prefer to enable a previously disabled user, if one exists.
  # Otherwise, it newly creates the user.
  global secrets
  endpoint = "%s/api/entities/academics-create-or-update" % (secrets['hostname'])
  student = S3.get_student_from_andrewid(andrewId)
  params = {
    'email': "%s@andrew.cmu.edu" % andrewId,
    'firstName': student.commonName,
    'lastName': student.lastName,
    'eppn': "%s@andrew.cmu.edu" % andrewId
  }
  headers = {
    'Content-Type': 'application/json',
    'api_key': secrets['api_key']
  }
  req = urllib.request.Request(endpoint, data=json.dumps(params).encode(), headers=headers, method='POST')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
  except urllib.error.HTTPError as e:
    error = json.loads(e.read().decode())
    raise Exception("Skylab error %s: %s\n%s" % (error['errorCode'], error['errorMsg'], error['errorDetails']))

def enable_user(andrewId):
  # This endpoint only operates on previously disabled users.
  global secrets
  endpoint = "%s/api/entities/academics-enable" % (secrets['hostname'])
  params = {
    'eppn': "%s@andrew.cmu.edu" % andrewId
  }
  headers = {
    'Content-Type': 'application/json',
    'api_key': secrets['api_key']
  }
  req = urllib.request.Request(endpoint, data=json.dumps(params).encode(), headers=headers, method='POST')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
  except urllib.error.HTTPError as e:
    error = json.loads(e.read().decode())
    raise Exception("Skylab error %s: %s\n%s" % (error['errorCode'], error['errorMsg'], error['errorDetails']))

def disable_user(andrewId):
  global secrets
  endpoint = "%s/api/entities/academics-disable" % (secrets['hostname'])
  params = {
    'eppn': "%s@andrew.cmu.edu" % andrewId
  }
  headers = {
    'Content-Type': 'application/json',
    'api_key': secrets['api_key']
  }
  req = urllib.request.Request(endpoint, data=json.dumps(params).encode(), headers=headers, method='POST')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
  except urllib.error.HTTPError as e:
    error = json.loads(e.read().decode())
    raise Exception("Skylab error %s: %s\n%s" % (error['errorCode'], error['errorMsg'], error['errorDetails']))


def __search_users(search_parameters):
  global secrets
  num_remaining = __count_users(search_parameters)
  page_size = 100
  page_num = 0
  users = []
  while num_remaining > 0:
    page_num += 1
    num_remaining -= min(num_remaining, page_size)
    parameters = {
      'pageSize': page_size,
      'pageNumber': page_num,
      'sortBy': '_email',
      'order': 'ASC'
    }
    parameters.update(search_parameters)
    endpoint = "%s/api/entities/academics-list?%s" % (secrets['hostname'], urllib.parse.urlencode(parameters))
    headers = {
      'Content-Type': 'application/json',
      'api_key': secrets['api_key']
    }
    req = urllib.request.Request(endpoint, data=json.dumps(parameters).encode(), headers=headers, method='GET')
    try:
      resp = urllib.request.urlopen(req).read()
      resp_data = json.loads(resp.decode('utf-8'))
      users.extend([ user['email'] for user in resp_data['payload'] ])
    except urllib.error.HTTPError as e:
      raise Exception("Skylab error %s: %s\n%s" % (error['errorCode'], error['errorMsg'], error['errorDetails']))
  return users

def __count_users(search_parameters):
  global secrets
  parameters = search_parameters
  endpoint = "%s/api/entities/academics-count?%s" % (secrets['hostname'], urllib.parse.urlencode(parameters))
  headers = {
    'Content-Type': 'application/json',
    'api_key': secrets['api_key']
  }
  req = urllib.request.Request(endpoint, data=json.dumps(parameters).encode(), headers=headers, method='GET')
  try:
    resp = urllib.request.urlopen(req).read()
    resp_data = json.loads(resp.decode('utf-8'))
    return resp_data['payload']
  except urllib.error.HTTPError as e:
    raise Exception("Skylab error %s: %s\n%s" % (error['errorCode'], error['errorMsg'], error['errorDetails']))
