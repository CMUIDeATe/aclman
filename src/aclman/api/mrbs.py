import datetime
import subprocess
import re

from ..models import *
from .. import config_handler
from . import s3 as S3

secrets = None

def load_secrets():
  global secrets
  secrets = config_handler.get_secrets('mrbs_db')
  secrets['domain'] = 'andrew.cmu.edu'

def execute(stmt):
  if secrets is None:
    load_secrets()

  return subprocess.check_output(["mysql", "-h", secrets['hostname'], "-s", "-N", "-u", secrets['username'], "-p%s" % secrets['password'], "-e", stmt]).decode('utf-8')

def get_members(roomId):
  if secrets is None:
    load_secrets()

  rows = execute("SELECT user_name FROM mrbs.mrbs_permissions WHERE room_id = \'%d\';" % roomId)
  return { re.sub('@%s$' % secrets['domain'], '', x) for x in rows.splitlines() }

def add_member(roomId, member):
  if secrets is None:
    load_secrets()

  # First, determine if the user is in the MRBS database at all.
  eppn = "%s@%s" % (member, secrets['domain'])
  count = int( execute("SELECT count(id) FROM mrbs.mrbs_users WHERE user_login = \"%s\";" % eppn) )
  # Add them if they're not.
  if count == 0:
    execute("INSERT INTO mrbs.mrbs_users (user_login, user_pass, user_nicename, user_email, display_name, level, affiliation, user_registered) VALUES (\"%s\", \"%s\", \"%s\", \"%s\", \"%s\", \"1\", \"C\", \"%s\");" % (eppn, member, member, eppn, S3.get_student_from_andrewid(member).fullDisplayName, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    # NOTE: `user_pass` is not actually used since MRBS login is controlled
    # by Shibboleth.

  # Now, provide the permission.
  execute("INSERT INTO mrbs.mrbs_permissions (user_name, room_id) VALUES (\"%s\", \"%d\");" % (eppn, roomId))

def remove_member(roomId, member):
  if secrets is None:
    load_secrets()

  eppn = "%s@%s" % (member, secrets['domain'])
  execute("DELETE FROM mrbs.mrbs_permissions WHERE user_name = \"%s\" AND room_id = \"%d\";" % (eppn, roomId))
