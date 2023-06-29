from .. import config_handler
from .. import helpers
from ..api import grouper as Grouper


group_mappings = config_handler.get_config('grouper_groups.eligibility')


def get_user(andrewId):
  group_data = {'timestamp': helpers.now().isoformat(),
                'eligibility_groups': {}
               }
  for group in group_mappings:
    group_id = group_mappings[group]
    group_data['eligibility_groups'][group] = Grouper.has_member(group_id, andrewId)
  return group_data

