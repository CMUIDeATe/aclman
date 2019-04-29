import os
import errno
from json import JSONEncoder

from aclman.models import *

# From https://stackoverflow.com/a/600612/782129, 2019-01-13
def mkdir_p(path):
  try:
    os.makedirs(path)
  except OSError as exc:
    if exc.errno == errno.EEXIST and os.path.isdir(path):
      pass
    else:
      raise

# From https://stackoverflow.com/a/3768975/782129, 2019-04-25
class CustomJSONEncoder(JSONEncoder):
  def default(self, obj):
    if isinstance(obj, (Section, Privilege, PrivilegeType)):
      return str(obj)
    if isinstance(obj, Student):
      return {'firstName': obj.firstName, 'preferredName': obj.preferredName, 'lastName': obj.lastName, 'bioUrl': obj.bioUrl, 'cardId': obj.cardId}
    return JSONEncoder.default(self, obj)
