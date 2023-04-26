import functools
import datetime
import calendar
import xml.etree.ElementTree as ET
import xml.dom.minidom

@functools.total_ordering
class Semester:
  def __init__(self, semester):
    self.semester = semester
    self.sem_type = self.semester[0]
    if self.sem_type in ['M', 'N', 'U']:
      self.sem_type = 'U'
    self.year_code = self.semester[1:]
    # Create a normalized semester code:
    self.semester_normalized = "%s%s" % (self.sem_type, self.year_code)

    # Coerce two-digit year from semester code to a full, four-digit year.
    self.year = datetime.datetime.strptime(self.year_code, '%y').year

    # SPRING TERM - hinges on end date
    # Typically ends on the Tuesday which is 5 days prior to Commencement.
    # - Through S20, term starts on the Monday which is 120 days earlier (15-week term plus Spring Break).
    # - S21 is a special case (see below).
    # - From S22, term starts on the Monday which is 113 days earlier (14-week term plus Spring Break).
    if self.sem_type == 'S':
      end_date = self.__commencement() - datetime.timedelta(days=5)
      if self.year <= 2020:
        start_date = end_date - datetime.timedelta(days=120)
      else:
        start_date = end_date - datetime.timedelta(days=113)
      # Sometimes this calculation causes the start date to fall on MLK Day, in
      # which case classes actually begin the following day.
      if start_date == self.__mlk_day():
        start_date += datetime.timedelta(days=1)
    # SUMMER TERM - hinges on start date
    # Typically starts on the Monday which is 1 day after Commencement.
    # - Through U20, term ends on the Friday which is 81 days later (12-week term).
    # - U21 and U22 are special cases (see below).
    # - From U23, term ends on the Friday which is 88 days later (12-week term plus Summer Break).
    elif self.sem_type == 'U':
      start_date = self.__commencement() + datetime.timedelta(days=1)
      if self.year <= 2021:
        end_date = start_date + datetime.timedelta(days=81)
      else:
        end_date = start_date + datetime.timedelta(days=88)
    # FALL TERM - hinges on start date
    # Typically starts on the Monday between 25 and 31 August.
    # - Through F20, term ends on the Monday which is 112 days later (15-week term).
    # - F21 is a special case (see below).
    # - From F22, term ends on the Monday which is 112 days later (14-week term plus Fall Break).
    elif self.sem_type == 'F':
      first_sun = self.__first_sunday_of_month(self.year, 8)
      if first_sun <= 2:
        start_date = datetime.date(self.year, 8, first_sun + 29)
      else:
        start_date = datetime.date(self.year, 8, first_sun + 22)
      end_date = start_date + datetime.timedelta(days=112)
    # If it's an unknown semester type, something is wrong.
    else:
      raise ValueError("Unknown semester type for '%s'" % semester)

    # Override for special cases:
    special_cases = { # S21 Covid adjustments introduce a 14-week semester,
		      # remove Spring Break, and shift Commencement 7 days
		      # later.  This shifts the start 21 days later than usual,
		      # and the end 7 days later.
                      'S21': ( datetime.date(2021,  2,  1), datetime.date(2021,  5, 18) ),
		      # U21 Covid adjustments shift Commencement, and thus the
		      # entire term, 7 days later; however, the simultaneous
		      # introduction of the Juneteenth holiday (observed on a
		      # Friday) moves the start of the term to the preceeding
		      # Friday, only 4 days later than usual.
                      'U21': ( datetime.date(2021,  5, 21), datetime.date(2021,  8, 13) ),
		      # F21 introduces a more permanent 14-week semester but
		      # not a Fall Break.  This would result in the term ending
		      # 7 days earlier than usual, but exams extend one day to
		      # the following Tuesday, only 6 days earlier than usual.
                      'F21': ( datetime.date(2021,  8, 30), datetime.date(2021, 12, 14) ),
		      # U22 has all holidays (Memorial Day, Juneteenth,
		      # Independence Day) observed on Mondays, requiring the
		      # term to extend to the following Monday.
                      'U22': ( datetime.date(2022,  5, 16), datetime.date(2022,  8, 15) )
                    }
    if self.semester_normalized in special_cases:
      (start_date, end_date) = special_cases[self.semester_normalized]

    # Convert the above dates into full datetimes.
    self.start = datetime.datetime( start_date.year, start_date.month, start_date.day, 0, 0, 0 )
    self.end = datetime.datetime( end_date.year, end_date.month, end_date.day, 23, 59, 59 )

  # Return the previous semester in sequence.
  # NOTE: This will eventually wrap due to coercion of two-digit years.
  def previous(self):
    if self.sem_type == 'S':
      prev_sem = "F%2d" % ( int(self.year_code) - 1 % 100 )
    elif self.sem_type == 'U':
      prev_sem = "S%2d" % int(self.year_code)
    elif self.sem_type == 'F':
      prev_sem = "U%2d" % int(self.year_code)
    # If it's an unknown semester type, something is wrong.
    else:
      raise ValueError("Unknown semester type for '%s'" % semester)

    return Semester(prev_sem)

  # Return the next semester in sequence.
  # NOTE: This will eventually wrap due to coercion of two-digit years.
  def next(self):
    if self.sem_type == 'S':
      next_sem = "U%2d" % int(self.year_code)
    elif self.sem_type == 'U':
      next_sem = "F%2d" % int(self.year_code)
    elif self.sem_type == 'F':
      next_sem = "S%2d" % ( int(self.year_code) + 1 % 100 )
    # If it's an unknown semester type, something is wrong.
    else:
      raise ValueError("Unknown semester type for '%s'" % semester)

    return Semester(next_sem)

  def __str__(self):
    return self.semester

  def __eq__(self, other):
    return self.start == other.start

  def __lt__(self, other):
    return self.start < other.start

  def __hash__(self):
    return hash(self.semester)

  def __first_sunday_of_month(self, year, month):
    return calendar.monthcalendar(year, month)[0][calendar.SUNDAY]

  # MLK Day for this year
  def __mlk_day(self):
    first_sun = self.__first_sunday_of_month(self.year, 1)
    # The third Monday in January.
    if first_sun == 7:
      return datetime.date(self.year, 1, first_sun + 8)
    else:
      return datetime.date(self.year, 1, first_sun + 15)
  # Commencement date for this year
  def __commencement(self):
    first_sun = self.__first_sunday_of_month(self.year, 5)
    # Beginning 2023, the second Sunday in May.
    if self.year >= 2023:
      return datetime.date(self.year, 5, first_sun + 7)
    # Through 2022, the third Sunday in May.
    else:
      return datetime.date(self.year, 5, first_sun + 14)

@functools.total_ordering
class Purpose:
  def __eq__(self, other):
    return self.purpose_sort_order() == other.purpose_sort_order()

  def __lt__(self, other):
    return self.purpose_sort_order() < other.purpose_sort_order()


@functools.total_ordering
class Section(Purpose):
  def __init__(self, semester, course, section):
    # Convert semester to a Semester object if it is passed, e.g., as a string.
    if isinstance(semester, Semester):
      self.semester = semester
    else:
      self.semester = Semester(semester)
    self.course = course
    self.section = section

  def __str__(self):
    return "%s-%s-%s" % (self.semester, self.course, self.section)

  def purpose_sort_order(self):
    # Sort Sections chronologically by semester, then lexically by course and
    # section.
    return (0, self.semester, self.course + '-' + self.section)

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
      return Privilege(a.privilege_type, str(a.start), str(a.end), sections)
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
  def __init__(self, data):
    self.data = data
    self.andrewId = data['biographical']['andrewId']
    self.firstName = data['biographical']['firstName']
    self.preferredName = data['biographical']['preferredName']
    self.lastName = data['biographical']['lastName']
    # Derive other names.
    if self.preferredName:
      self.commonName = self.preferredName
      self.allNames = "%s, %s (%s)" % (self.lastName, self.preferredName, self.firstName)
    else:
      self.commonName = self.firstName
      self.allNames = "%s, %s" % (self.lastName, self.firstName)
    self.fullName = "%s, %s" % (self.lastName, self.commonName)
    self.fullDisplayName = "%s %s" % (self.commonName, self.lastName)

    self.billable = data['academic']['billable']
    # TODO: Find out whether `hasHolds` and `holdDescriptions` might ever
    # contain any useful data.

  def set_bioId(self, bioId):
    self.data['biographical']['bioId'] = bioId

  def __str__(self):
    return "%-8s - %s" % (self.andrewId, self.allNames)


class CsGoldData:
  def __init__(self, comment):
    self.xml = ET.Element('AccessAssignments')
    self.xml.append(ET.Comment(comment))

  def append_access_assignment(self, andrewId, groupId, start_date, end_date, comment):
    priv_asgn = ET.SubElement(self.xml, 'AccessAssignment')

    priv_asgn_andrewid = ET.SubElement(priv_asgn, 'AndrewID')
    priv_asgn_group = ET.SubElement(priv_asgn, 'GroupNumber')
    priv_asgn_start = ET.SubElement(priv_asgn, 'StartDate')
    priv_asgn_end = ET.SubElement(priv_asgn, 'EndDate')
    priv_asgn_comment = ET.SubElement(priv_asgn, 'Comment')

    priv_asgn_andrewid.text = andrewId
    priv_asgn_group.text = groupId
    priv_asgn_start.text = start_date
    priv_asgn_end.text = end_date
    priv_asgn_comment.text = comment

  def export_xml(self):
    xmldata = xml.dom.minidom.parseString(ET.tostring(self.xml))
    return xmldata.toprettyxml(indent="  ")
