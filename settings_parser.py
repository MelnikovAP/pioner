from settings_constants import *
from scan_params import ScanParams
from daq_params import DaqParams
from ai_params import AiParams
from ao_params import AoParams
from constants import MAX_SCAN_SAMPLE_RATE
from settings import Settings
from utils import is_int_or_raise


class SettingsParser:
    def __init__(self, path: str):
        json_dict = Settings(path).get_json()
        if SETTINGS_FIELD not in json_dict:
            raise ValueError("No '{}' field found in the settings file.".format(SETTINGS_FIELD))
        else:
            self._settings_dict = json_dict[SETTINGS_FIELD]
            for field in [DAQ_FIELD, SCAN_FIELD, AI_FIELD, AO_FIELD]:
                if field not in self._settings_dict:
                    raise ValueError("No '{}' field found in the settings file.".format(field))

        # only in that order
        self._parse_scan_params()
        self._parse_daq_params()
        self._parse_ai_params()
        self._parse_ao_params()

    def get_scan_params(self) -> ScanParams:
        return self._scan_params

    def get_daq_params(self) -> DaqParams:
        return self._daq_params

    def get_ai_params(self) -> AiParams:
        return self._ai_params

    def get_ao_params(self) -> AoParams:
        return self._ao_params

    def _parse_scan_params(self):
        self._scan_params = ScanParams()
        scan_dict = self._settings_dict[SCAN_FIELD]

        if SAMPLE_RATE_FIELD in scan_dict:
            sample_rate = scan_dict[SAMPLE_RATE_FIELD]
            if is_int_or_raise(sample_rate):
                self._scan_params.sample_rate = min(int(sample_rate), MAX_SCAN_SAMPLE_RATE)

        if CHANNEL_COUNT_FIELD in scan_dict:
            channel_count = scan_dict[CHANNEL_COUNT_FIELD]
            if is_int_or_raise(channel_count):
                self._scan_params.channel_count = int(channel_count)

        if OPTIONS_FIELD in scan_dict:
            options = scan_dict[OPTIONS_FIELD]
            if isinstance(options, list):
                for option in options:
                    if is_int_or_raise(option):
                        self._scan_params.options = int(option)
            elif is_int_or_raise(options):
                self._scan_params.options = int(options)
        self._scan_params.samples_per_channel = self._scan_params.channel_count * self._scan_params.sample_rate

    def _parse_daq_params(self):
        self._daq_params = DaqParams()
        daq_dict = self._settings_dict[DAQ_FIELD]

        if INTERFACE_TYPE_FIELD in daq_dict:
            interface_types = daq_dict[INTERFACE_TYPE_FIELD]
            if isinstance(interface_types, list):
                for interface_type in interface_types:
                    if is_int_or_raise(interface_type):
                        self._daq_params.interface_type = int(interface_type)
            elif is_int_or_raise(interface_types):
                self._daq_params.interface_type = int(interface_types)
        else:
            raise ValueError("No '{}' field found in the settings file.".format(INTERFACE_TYPE_FIELD))

        if CONNECTION_CODE_FIELD in daq_dict:
            connection_code = daq_dict[CONNECTION_CODE_FIELD]
            if is_int_or_raise(connection_code):
                self._daq_params.connection_code = int(connection_code)

    def _parse_ai_params(self):
        self._ai_params = AiParams()
        ai_dict = self._settings_dict[AI_FIELD]

        if RANGE_ID_FIELD in ai_dict:
            range_id = ai_dict[RANGE_ID_FIELD]
            if is_int_or_raise(range_id):
                self._ai_params.range_id = int(range_id)

        if LOW_CHANNEL_FIELD in ai_dict:
            low_channel = ai_dict[LOW_CHANNEL_FIELD]
            if is_int_or_raise(low_channel):
                self._ai_params.low_channel = int(low_channel)

        if HIGH_CHANNEL_FIELD in ai_dict:
            high_channel = ai_dict[HIGH_CHANNEL_FIELD]
            if is_int_or_raise(high_channel):
                self._ai_params.high_channel = int(high_channel)

        if INPUT_MODE_FIELD in ai_dict:
            input_mode = ai_dict[INPUT_MODE_FIELD]
            if is_int_or_raise(input_mode):
                self._ai_params.input_mode = int(input_mode)

        if SCAN_FLAGS_FIELD in ai_dict:
            scan_flags = ai_dict[SCAN_FLAGS_FIELD]
            if isinstance(scan_flags, list):
                for scan_flag in scan_flags:
                    if is_int_or_raise(scan_flag):
                        self._ai_params.scan_flags = int(scan_flag)
            elif is_int_or_raise(scan_flags):
                self._ai_params.scan_flags = int(scan_flags)

    def _parse_ao_params(self):
        self._ao_params = AoParams()
        ao_dict = self._settings_dict[AO_FIELD]

        if RANGE_ID_FIELD in ao_dict:
            range_id = ao_dict[RANGE_ID_FIELD]
            if is_int_or_raise(range_id):
                self._ao_params.range_id = int(range_id)

        if LOW_CHANNEL_FIELD in ao_dict:
            low_channel = ao_dict[LOW_CHANNEL_FIELD]
            if is_int_or_raise(low_channel):
                self._ao_params.low_channel = int(low_channel)

        if HIGH_CHANNEL_FIELD in ao_dict:
            high_channel = ao_dict[HIGH_CHANNEL_FIELD]
            if is_int_or_raise(high_channel):
                self._ao_params.high_channel = int(high_channel)

        if SCAN_FLAGS_FIELD in ao_dict:
            scan_flags = ao_dict[SCAN_FLAGS_FIELD]
            if isinstance(scan_flags, list):
                for scan_flag in scan_flags:
                    if is_int_or_raise(scan_flag):
                        self._ao_params.scan_flags = int(scan_flag)
            elif is_int_or_raise(scan_flags):
                self._ao_params.scan_flags = int(scan_flags)


if __name__ == '__main__':
    try:
        _path = "./test_settings.json"
        parser = SettingsParser(_path)

        _scan_params = parser.get_scan_params()
        _daq_params = parser.get_daq_params()
        _ai_params = parser.get_ai_params()
        _ao_params = parser.get_ao_params()

    except BaseException as e:
        print(e)
