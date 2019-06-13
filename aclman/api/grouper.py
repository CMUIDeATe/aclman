import sys
import urllib.request
import base64
import json

secrets = {}

def set_secrets(s):
  global secrets
  secrets = s

  auth_cred = ('%s:%s' % (secrets['username'], secrets['password']))
  auth_str = base64.encodebytes(auth_cred.encode('ascii'))[:-1].decode('utf-8')
  auth_header = { 'Authorization': 'Basic %s' % auth_str }
  secrets['auth_header'] = auth_header


def get_members(groupId):
  global secrets
  endpoint = "%s/grouper-ws/servicesRest/json/v2_2_001/groups/%s/members" % (secrets['hostname'], urllib.parse.quote_plus(groupId))
  req = urllib.request.Request(endpoint, None, secrets['auth_header'], method='GET')
  try:
    resp = urllib.request.urlopen(req).read()
    group_data = json.loads(resp.decode('utf-8'))
    try:
      subject_data = group_data['WsGetMembersLiteResult']['wsSubjects']
    except KeyError:
      subject_data = []
    return { x['id'] for x in subject_data }
  except urllib.error.HTTPError as e:
    sys.stderr.write("Grouper error: %s\n" % e)
    return set()

def add_member(groupId, member):
  global secrets
  endpoint = "%s/grouper-ws/servicesRest/json/v2_2_001/groups/%s/members/%s" % (secrets['hostname'], urllib.parse.quote_plus(groupId), member)
  req = urllib.request.Request(endpoint, None, secrets['auth_header'], method='PUT')
  try:
    resp = urllib.request.urlopen(req).read()
  except urllib.error.HTTPError as e:
    raise e

def remove_member(groupId, member):
  global secrets
  endpoint = "%s/grouper-ws/servicesRest/json/v2_2_001/groups/%s/members/%s" % (secrets['hostname'], urllib.parse.quote_plus(groupId), member)
  req = urllib.request.Request(endpoint, None, secrets['auth_header'], method='DELETE')
  try:
    resp = urllib.request.urlopen(req).read()
  except urllib.error.HTTPError as e:
    raise e
