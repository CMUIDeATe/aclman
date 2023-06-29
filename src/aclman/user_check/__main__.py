#!/usr/bin/python3

import json

from ..cli import CliParser
from .. import helpers

from . import enrollment
from . import laser_groups
from . import bioraft_trainings


cli = CliParser('ACLMAN user check', "python -m aclman.user_check")
cli.option(metavar='ANDREWID', action='store', dest='andrewId', default=None, help="the Andrew ID of the user to check")
cli.option('--attr', '--attribute', '-a', metavar='ATTR', action='store', dest='attribute', default=None, help="specify a subtree of the user's data to return")
cli.option('--no-pretty', action='store_false', dest='pretty', default=True, help="don't pretty-print the JSON output")
args = cli.parse()


andrewId = args.andrewId
user_data = {}
user_data['errors'] = []

# Check enrollment data from S3.
# TODO: Separate out biographical/academic from sections/privileges.
try:
  enrollment_data = enrollment.get_user(andrewId)
except Exception as e:
  user_data['errors'].append(str(e))
  enrollment_data = {}
user_data['enrollment'] = enrollment_data

# Check laser cutter eligibility status as reported by Grouper.
try:
  laser_data = laser_groups.get_user(andrewId)
except Exception as e:
  user_data['errors'].append(str(e))
  laser_data = {}
user_data['laser_groups'] = laser_data

# Check BioRAFT trainings.
try:
  bioraft_data = bioraft_trainings.get_user(andrewId)
except Exception as e:
  user_data['errors'].append(str(e))
  bioraft_data = {}
user_data['bioraft_trainings'] = bioraft_data


if args.attribute is None:
  selected_data = user_data
else:
  ## TODO: Specifying an attribute does not constrain what data gets loaded
  ## above, only what gets returned, so there is no performance benefit.
  try:
    selected_data = helpers.subtree(user_data, args.attribute)
  except KeyError as e:
    raise KeyError("No such attribute '%s' in data for user '%s'." % (args.attribute, andrewId))

# Output as JSON.
if args.pretty:
  print(json.dumps(selected_data, indent=2))
else:
  print(json.dumps(selected_data))
