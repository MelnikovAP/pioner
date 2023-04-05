from settings import Settings
from typing import Dict, Any

from segment_data import SegmentType
from utils.data_types import DataType


# TODO: use other types instead of inner dicts
profiles_table = {
    0: {
        SegmentType.SINE: {}  # TODO: think about it
    },
    1: {
        SegmentType.RAMP: {
            DataType.TIME: [0., 3000.],
            DataType.VOLT: [0., 5.]
        }
    },
    2: {
        SegmentType.ISO: {
            DataType.VOLT: 5.
        }
    }
}


class ProfileTableConverter:
    def __init__(self,
                 profiles_dict: Dict[int, Dict[SegmentType, Dict[DataType, Any]]],
                 settings: Settings):
        self._profiles_dict = profiles_dict
        self._settings = settings

        self._verify_and_parse()

    def _verify_and_parse(self):
        for channel, profile_dict in self._profiles_dict.items():
            profile_type, profile_data = profile_dict.items()  # TODO: fix
            if profile_type == SegmentType.NONE:
                raise ValueError("OutProfileType.NONE for channel {}".format(channel))
            elif profile_type == SegmentType.ISO:
                pass
            elif profile_type == SegmentType.RAMP:
                pass
            elif profile_type == SegmentType.SINE:
                pass
            else:
                raise ValueError("Unexpected profile type for channel {}".format(channel))


if __name__ == "__main__":
    pass
