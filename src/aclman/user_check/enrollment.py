import pathlib
import json

from .. import config_handler
from .. import helpers
from ..api import s3 as S3


jsondata_dir = config_handler.get_config('output_dirs.jsondata')
jsondata_path = pathlib.Path(config_handler.cwd, jsondata_dir, 'latest.json').resolve()


def get_user(andrewId):
  try:
    with open(jsondata_path, 'r') as jsonfile:
      jsondata = json.load(jsonfile)

    cached_data = jsondata['users'][andrewId]
    timestamp = jsondata['timestamp']

    enrollment_data = {
      'timestamp': timestamp,
      'ideate_student': len(cached_data['sections']) > 0,
      'academic': cached_data['academic'],
      'biographical': cached_data['biographical'],
      'privileges': cached_data['privileges'],
      'sections': cached_data['sections']
    }
  except KeyError:
    # If not cached as an IDeATe student, send a live query to S3 for academic
    # and biographical information.
    timestamp = helpers.now().isoformat()

    try:
      s3_data = S3.get_student_from_andrewid(andrewId)
      enrollment_data = {
        'timestamp': timestamp,
        'ideate_student': False,
        'academic': s3_data.data['academic'],
        'biographical': s3_data.data['biographical'],
        'privileges': [],
        'sections': []
      }
    except KeyError:
      # If there's no S3 record, they're not a student.  Give up.
      # TODO: Get more biographical information from LDAP.
      raise KeyError("No S3 student record for user '%s'" % andrewId)

  return enrollment_data
