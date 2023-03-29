from settings import Settings
from typing import Dict, Any

from data_types import DataType, OutProfileType






# # TODO: use OrderedDict
# # TODO: use other types instead of inner dicts
# profiles_table = {
#     0: {
#         OutProfileType.SINE: {}  # TODO: think about it
#     },
#     1: {
#         OutProfileType.PROFILE: {
#             DataType.TIME: [0., 100., 1100., 1900., 2900., 3000.],
#             DataType.VOLT: [0., 0., 5., 5., 0., 0.]
#         }
#     },
#     2: {
#         OutProfileType.ISO: {
#             DataType.VOLT: 5.
#         }
#     },
#     3: {
#         OutProfileType.RAMP: {
#             DataType.TIME: [0., 3000.],
#             DataType.VOLT: [0., 5.]
#         }
#     }
# }
#
# # TODO: think about profiles of different duration
#
#
# class ProfileTableConverter:
#     def __init__(self,
#                  profiles_dict: Dict[int, Dict[OutProfileType, Dict[DataType, Any]]],
#                  settings: Settings):
#         self._profiles_dict = profiles_dict
#         self._settings = settings
#
#         self._verify_and_parse()
#
#     def _verify_and_parse(self):
#         for channel, profile_dict in self._profiles_dict.items():
#             profile_type, profile_data = profile_dict.items()  # TODO: fix
#             if profile_type == OutProfileType.NONE:
#                 raise ValueError("OutProfileType.NONE for channel {}".format(channel))
#             elif profile_type == OutProfileType.ISO:
#                 pass
#             elif profile_type == OutProfileType.RAMP:
#                 pass
#             elif profile_type == OutProfileType.PROFILE:
#                 pass
#             elif profile_type == OutProfileType.SINE:
#                 pass
#             else:
#                 raise ValueError("Unexpected profile type for channel {}".format(channel))




if __name__ == "__main__":
    pass
