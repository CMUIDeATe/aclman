import sys
import argparse

# The CliParser class is a wrapper on argparse.ArgumentParser in order to
# streamline potentially complex argument requirements and validation.

class CliParser():
  parser = argparse.ArgumentParser()

  def __init__(self, description):
    self.parser = argparse.ArgumentParser(description=description)

  def option(self, *args, **kwargs):
    self.parser.add_argument(*args, **kwargs)

  def file_read_option(self, *args, **kwargs):
    self.parser.add_argument(*args, type=argparse.FileType('r'), **kwargs)

  def parse(self):
    args = self.parser.parse_args()
    return args
