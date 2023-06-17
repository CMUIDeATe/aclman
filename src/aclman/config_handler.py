import pathlib
import yaml

from . import helpers


cwd = pathlib.Path.cwd()
default_config_dir = pathlib.Path(cwd, 'config').resolve()

config_path = None
config_data = None

secrets_path = None
secrets_data = None


def set_config_path(path=None):
  global config_path, config_data

  if path is None:
    path = pathlib.Path(default_config_dir, 'config.yaml')
  else:
    path = pathlib.Path(path)

  if not path.is_file():
    raise FileNotFoundError("No config file found at '%s'" % path)
  config_path = path
  config_data = None

def set_secrets_path(path=None):
  global secrets_path, secrets_data

  if path is None:
    path = pathlib.Path(default_config_dir, 'secrets.yaml')
  else:
    path = pathlib.Path(path)

  if not path.is_file():
    raise FileNotFoundError("No secrets file found at '%s'" % path)
  secrets_path = path
  secrets_data = None


def get_config(subtree=None):
  global config_data

  if config_path is None:
    set_config_path()
  if config_data is None:
    with open(config_path, 'r') as config_file:
      config_data = yaml.safe_load(config_file)

  if subtree is None:
    return config_data
  try:
    delim = '.'
    parts = subtree.split(delim)
    return helpers.subtree(config_data, parts, delim)
  except KeyError as e:
    raise e

def get_secrets(subtree=None):
  global secrets_data

  if secrets_path is None:
    set_secrets_path()
  if secrets_data is None:
    with open(secrets_path, 'r') as secrets_file:
      secrets_data = yaml.safe_load(secrets_file)

  if subtree is None:
    return secrets_data
  try:
    delim = '.'
    parts = subtree.split(delim)
    return helpers.subtree(secrets_data, parts, delim)
  except KeyError as e:
    raise e
