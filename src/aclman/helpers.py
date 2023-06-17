import functools
import os
import errno
import datetime
import urllib.request
import urllib.error
import json
from json import JSONEncoder

from aclman.models import *


def now():
  return datetime.datetime.now(datetime.timezone.utc).astimezone()

def business_semester(t=None):
  if t == None:
    t = datetime.datetime.now()
  # Return the current semester (as of the specified date, if applicable) for
  # business purposes, e.g.:
  # - If classes are in session, return the current semester.
  # - If classes are NOT in session, return the NEXT (upcoming) semester.

  # Check against each semester ending within the calendar year.
  year_code = '{:02d}'.format(t.year % 100)
  for semester in [Semester('S%s' % year_code), Semester('U%s' % year_code), Semester('F%s' % year_code)]:
    if t <= semester.end:
      return semester
  # If they're all done, return the following Spring term.
  return Semester('S{:02d}'.format((t.year + 1) % 100))

# Adapted from https://stackoverflow.com/a/31033676, 2023-06-21
def subtree(tree, path, delim='.'):
  def __get_element(state, el):
    (tree, traversed) = state
    # Convert numeric strings of element names to ints.
    if el.isnumeric():
      el = int(el)
    # Get the specified element and record a level of path-traversal.
    try:
      value = tree[el]
    except KeyError as e:
      raise KeyError("No element '%s' found when traversing subtree '%s'." % (el, delim.join(traversed)))
    except TypeError as e:
      raise KeyError("Subtree '%s' could not be subscripted for element '%s'." % (delim.join(traversed), el))
    return (value, traversed + (el,))

  # Allow traversal of element paths passed as a delimited string or a list of
  # parts.
  if isinstance(path, list):
    parts = path
  else:
    parts = path.split(delim)
  # Recursively traverse the element path.
  try:
    (data, parts_traversed) = functools.reduce(__get_element, parts, (tree, ()))
  except KeyError as e:
    raise e
  return data

# From https://stackoverflow.com/a/3768975/782129, 2019-04-25
class CustomJSONEncoder(JSONEncoder):
  def default(self, obj):
    if isinstance(obj, (Semester, Section, Privilege, PrivilegeType)):
      return str(obj)
    if isinstance(obj, Student):
      return {'firstName': obj.firstName, 'preferredName': obj.preferredName, 'lastName': obj.lastName}
    return JSONEncoder.default(self, obj)

class CustomHTTPErrorHandler(urllib.request.HTTPDefaultErrorHandler):
  def http_error_default(self, req, fp, code, msg, hdrs):
    if req.host == "creator.zoho.com" and hdrs['Content-Type'].startswith("application/json"):
      s = b''.join(fp).decode()
      resp = json.loads(s)
      # See https://www.zoho.com/creator/help/api/v2/status-codes.html
      if resp['code'] == 3100: # No records found for the given criteria.
        raise IndexError
      else:
        raise Exception("Zoho error code %d: '%s'" % (resp['code'], resp['message']))
    else:
      s = b''.join(fp).decode()
      resp = json.loads(s)
    raise urllib.error.HTTPError(req.full_url, code, msg, hdrs, fp)
