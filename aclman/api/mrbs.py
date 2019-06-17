import subprocess
import re

secrets = {}

def set_secrets(s):
  global secrets
  secrets = s
  secrets['hostname'] = 'localhost'
  secrets['domain'] = 'andrew.cmu.edu'

def execute(stmt):
  global secrets
  return subprocess.check_output(["mysql", "-h", secrets['hostname'], "-s", "-N", "-u", secrets['username'], "-p%s" % secrets['password'], "-e", stmt]).decode('utf-8')

def get_members(roomId):
  global secrets
  rows = execute("SELECT user_name FROM mrbs.mrbs_permissions WHERE room_id = \'%d\';" % roomId)
  return { re.sub('@%s$' % secrets['domain'], '', x) for x in rows.splitlines() }

def add_member(roomId, member):
  global secrets
  # First, determine if the user is in the MRBS database at all.
  eppn = "%s@%s" % (member, secrets['domain'])
  count = execute("SELECT count(id) FROM mrbs.mrbs_users WHERE user_login = \'%s\';" % eppn)
  # Add them if they're not.
  if count == 0:
    execute("INSERT INTO mrbs.mrbs_users user_login, user_pass, user_nicename, user_email, display_name, level, affiliation) VALUES (\'%s\', \'%s\', \'%s\', \'%s\', \'%s\', \'1\', \'C\');" % (eppn, member, member, eppn, NAME))
    # NOTE: `user_pass` is not actually used since MRBS login is controlled
    # by Shibboleth.
    # TODO: Make `display_name` useable.

  # Now, provide the permission.
  execute("INSERT INTO mrbs.mrbs_permissions (user_name, room_id) VALUES (\'%s\', \'%d\');" % (eppn, roomId))

def remove_member(roomId, member):
  global secrets
  eppn = "%s@%s" % (member, secrets['domain'])
  execute("DELETE FROM mrbs.mrbs_permissions WHERE user_name = \'%s\' AND room_id = \'%d\';" % (eppn, roomId))
