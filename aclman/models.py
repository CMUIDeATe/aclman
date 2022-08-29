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

    # Spring term typically ends on the Tuesday between 10 and 16 May,
    # and starts 120 days earlier:
    if self.sem_type == 'S':
      first_sun = self.__first_sunday_of_month(self.year, 5)
      end_date = datetime.date(self.year, 5, first_sun + 9)
      start_date = end_date - datetime.timedelta(days=120)
      # NOTE: Sometimes this causes the start date to fall on MLK Day,
      # in which case classes actually begin the following day.
    # Summer term typically ends on the Friday between 5 and 11 August,
    # and starts 81 days earlier:
    elif self.sem_type == 'U':
      first_sun = self.__first_sunday_of_month(self.year, 8)
      if first_sun == 7:
        end_date = datetime.date(self.year, 8, first_sun - 2)
      else:
        end_date = datetime.date(self.year, 8, first_sun + 5)
      start_date = end_date - datetime.timedelta(days=81)
    # Fall term typically ends on the Monday between 15 and 21 December,
    # and starts 112 days earlier:
    elif self.sem_type == 'F':
      first_sun = self.__first_sunday_of_month(self.year, 12)
      if first_sun == 7:
        end_date = datetime.date(self.year, 12, first_sun + 8)
      else:
        end_date = datetime.date(self.year, 12, first_sun + 15)
      start_date = end_date - datetime.timedelta(days=112)
    # If it's an unknown semester type, something is wrong.
    else:
      raise ValueError("Unknown semester type for '%s'" % semester)

    # Override for special cases:
    special_cases = { # AY2021 Covid adjustments
                      'S21': ( datetime.date(2021,  2,  1), datetime.date(2021,  5, 18) ),
                      'U21': ( datetime.date(2021,  5, 21), datetime.date(2021,  8, 13) ),
                      # 14-week semesters implemented beginning AY2022
                      # - F21 starts on same schedule, but ends 6 days earlier, on a Tuesday.
                      # - S22 ends on same schedule, but starts 7 days later (ignoring MLK Day).
                      'F21': ( datetime.date(2021,  8, 30), datetime.date(2021, 12, 14) ),
                      'S22': ( datetime.date(2022,  1, 17), datetime.date(2022,  5, 10) ),
                      # Juneteenth and Summer Break implemented for AY2022
                      # - U22 starts on same schedule, but ends 10 days later, on a Monday.
                      'U22': ( datetime.date(2022,  5, 16), datetime.date(2022,  8, 15) ),
                      # Fall break implemented beginning AY2023 restores
                      # original start/end pattern for F22.
                      # Commencement moved a week earlier in AY2023
                      # - S23 ends 7 days earlier.
                      # - U23 starts and ends 7 days earlier.  Summer Break
                      #   removed in AY2023 restores original length
                      #   (Juneteenth retained).
                      # TODO: See how spring/summer patterns stabilize before incorporating above.
                      'S23': ( datetime.date(2023,  1, 16), datetime.date(2023,  5,  9) ),
                      'U23': ( datetime.date(2023,  5, 15), datetime.date(2023,  8,  4) )
                    }
    if self.semester_normalized in special_cases:
      (start_date, end_date) = special_cases[self.semester_normalized]

    # Convert the above dates into full datetimes.
    self.start = datetime.datetime( start_date.year, start_date.month, start_date.day, 0, 0, 0 )
    self.end = datetime.datetime( end_date.year, end_date.month, end_date.day, 23, 59, 59 )

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
    if self.preferredName:
      return "%s - %s (%s)" % (self.andrewId, self.fullName, self.firstName)
    else:
      return "%s - %s" % (self.andrewId, self.fullName)


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
