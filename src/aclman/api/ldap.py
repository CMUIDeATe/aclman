import ldap3

from aclman.models import *

secrets = {}

def set_secrets(s):
  global secrets
  secrets = s


def fetch_ldap_data_from_andrewid(andrewId):
  global secrets
  server = ldap3.Server(secrets['hostname'])
  conn = ldap3.Connection(server, secrets['bind_dn'], secrets['password'], auto_bind=True)

  conn.search(search_base='ou=AndrewPerson,dc=andrew,dc=cmu,dc=edu', search_filter='(cmuAndrewId=%s)' % andrewId, attributes=['cmuAndrewId', 'eduPersonPrincipalName', 'eduPersonScopedAffiliation', 'mail', 'cn', 'sn', 'givenName', 'nickname', 'displayName', 'cmuDepartment', 'cmuStudentClass'])
  # TODO: Might be better to return None and put the try in Person to be like
  # S3 API
  try:
    ldap_entry = conn.entries[0]
    if ldap_entry['cn'] != 'Merged Person' or ldap_entry['displayName'] is None:
      return ldap_entry
    else:
      raise IndexError("Merged Person LDAP entry for '%s'" % andrewId)
  except IndexError:
    raise IndexError("No LDAP entry for '%s'" % andrewId)
