import os
import errno

# From https://stackoverflow.com/a/600612/782129, 2019-01-13
def mkdir_p(path):
  try:
    os.makedirs(path)
  except OSError as exc:
    if exc.errno == errno.EEXIST and os.path.isdir(path):
      pass
    else:
      raise
