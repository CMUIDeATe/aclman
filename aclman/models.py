import datetime

class Section:
  def __init__(self, semester, course, section):
    self.semester = semester
    self.course = course
    self.section = section

  def __str__(self):
    return "%s-%s-%s" % (self.semester, self.course, self.section)

  def __eq__(self, other):
    return (self.semester, self.course, self.section) == (other.semester, other.course, other.section)

  def __lt__(self, other):
    # If the semesters are the same, sort lexically by concatenating course and
    # section.
    if self.semester == other.semester:
      return self.course + '-' + self.section < other.course + '-' + other.section
    # Otherwise, sort chronologically by semester.
    months = {'S': 1, 'M': 6, 'N': 7, 'F': 9}
    self_term = 100*int(self.semester[1:]) + months[self.semester[0]]
    other_term = 100*int(other.semester[1:]) + months[other.semester[0]]
    return self_term < other_term

  def __hash__(self):
    return hash((self.semester, self.course, self.section))


class PrivilegeType:
  def __init__(self, key, value):
    self.key = key
    self.value = value

  def __str__(self):
    return "(%s,%s)" % (self.key, self.value)

  def __eq__(self, other):
    return (self.key, self.value) == (other.key, other.value)

  def __lt__(self, other):
    return (self.key, self.value) < (other.key, other.value)

  def __hash__(self):
    return hash((self.key, self.value))


class Privilege:
  def __init__(self, privilege_type, start, end, sections):
    t = datetime.datetime.now()
    self.privilege_type = privilege_type
    self.key = self.privilege_type.key
    self.value = self.privilege_type.value
    if start and start != "None":
      self.start = datetime.datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
      self.actual_start = self.start
    else:
      self.start = datetime.datetime(t.year - 25, 1, 1, 0, 0, 0)
      self.actual_start = None
    if end and end != "None":
      self.end = datetime.datetime.strptime(end, "%Y-%m-%d %H:%M:%S")
      self.actual_end = self.end
    else:
      self.end = datetime.datetime(t.year + 25, 12, 31, 23, 59, 59)
      self.actual_end = None
    self.sections = sections

  def __str__(self):
    if len(self.sections) >= 1:
      sections_string = ','.join(str(x) for x in self.sections)
    else:
      sections_string = ""
    return "(%s,(%s,%s),[%s])" % (self.privilege_type, self.start, self.end, sections_string)

  def __eq__(self, other):
    return (self.privilege_type, self.start, self.end, self.sections) == (other.privilege_type, other.start, other.end, other.sections)

  def __lt__(self, other):
    return (self.privilege_type, self.start, self.end, self.sections) < (other.privilege_type, other.start, other.end, other.sections)

  def replace_sections(self, sections):
    return Privilege(self.privilege_type, str(self.start), str(self.end), sections)

  def is_current(self, t=None):
    if t == None:
      t = datetime.datetime.now()
    # If the privilege is open-ended on both ends, then it is always considered
    # "current".
    if self.start == None and self.end == None:
      return True
    # Otherwise, evaluate at the specified timestamp (or now, if none was
    # specified).
    if self.end == None:
      return t >= self.start
    if self.start == None:
      return t <= self.end
    return t >= self.start and t <= self.end

  def coalesce(self, other):
    # Can only coalesce privileges of the same type.
    if self.privilege_type != other.privilege_type:
      raise ValueError("Cannot coalesce privileges %s and %s since they are not of the same type" % (self, other))
    a = min(self, other)
    b = max(self, other)
    sections = a.sections + b.sections
    # If they're considered equal, just combine the sections:
    if a == b:
      return Privilege(a.privilege_type, a.start, a.end, sections)
    # If periods overlap (or are 1 second apart), simply combine them:
    if b.start <= a.end + datetime.timedelta(seconds=1):
      return Privilege(a.privilege_type, str(min(a.start, b.start)), str(max(a.end, b.end)), sections)
    # If no overlap, prefer the one that is current:
    if a.is_current():
      return a
    if b.is_current():
      return b
    # If neither are current, prefer one that's in the future:
    t = datetime.datetime.now()
    if a.start > t:
      return a
    if b.start > t:
      return b
    # Otherwise, prefer the one least in the past:
    return b


class Student:
  def __init__(self, data, bio_url):
    self.data = data
    self.bioUrl = bio_url
    self.andrewId = data['andrewId']
    self.cardId = data['cardId']
    self.firstName = data['firstName']
    self.preferredName = data['preferredName']
    self.lastName = data['lastName']
    # Derive other names.
    if self.preferredName:
      self.commonName = self.preferredName
      self.allNames = "%s, %s (%s)" % (self.lastName, self.preferredName, self.firstName)
    else:
      self.commonName = self.firstName
      self.allNames = "%s, %s" % (self.lastName, self.firstName)
    self.fullName = "%s, %s" % (self.lastName, self.commonName)
    self.fullDisplayName = "%s %s" % (self.commonName, self.lastName)
    # TODO: Find out whether `hasHolds` and `holdDescriptions` might ever
    # contain any useful data.

  def __str__(self):
    if self.preferredName:
      return "%s - %s (%s)" % (self.andrewId, self.fullName, self.firstName)
    else:
      return "%s - %s" % (self.andrewId, self.fullName)
