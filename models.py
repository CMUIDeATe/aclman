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
