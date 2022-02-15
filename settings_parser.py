from settings_constants import *
from scan_params import ScanParams
from daq_params import DaqParams
from ai_params import AiParams
from ao_params import AoParams
from constants import MAX_SCAN_SAMPLE_RATE
from settings import Settings
from utils import is_int_or_raise, list_bitwise_or


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

        self._invalid_fields = []
        # only in that order
        self._parse_scan_params()
        self._parse_daq_params()
        self._parse_ai_params()
        self._parse_ao_params()
        self._check_invalid_fields()

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
        else:
            self._invalid_fields.append(SAMPLE_RATE_FIELD)

        if CHANNEL_COUNT_FIELD in scan_dict:
            channel_count = scan_dict[CHANNEL_COUNT_FIELD]
            if is_int_or_raise(channel_count):
                self._scan_params.channel_count = int(channel_count)
        else:
            self._invalid_fields.append(CHANNEL_COUNT_FIELD)

        if OPTIONS_FIELD in scan_dict:
            options = scan_dict[OPTIONS_FIELD]
            if isinstance(options, list):
                self._scan_params.options = list_bitwise_or(options)
            elif is_int_or_raise(options):
                self._scan_params.options = int(options)
        else:
            self._invalid_fields.append(OPTIONS_FIELD)
        self._scan_params.samples_per_channel = self._scan_params.channel_count * self._scan_params.sample_rate

    def _parse_daq_params(self):
        self._daq_params = DaqParams()
        daq_dict = self._settings_dict[DAQ_FIELD]

        if INTERFACE_TYPE_FIELD in daq_dict:
            interface_types = daq_dict[INTERFACE_TYPE_FIELD]
            if isinstance(interface_types, list):
                self._daq_params.interface_type = list_bitwise_or(interface_types)
            elif is_int_or_raise(interface_types):
                self._daq_params.interface_type = int(interface_types)
        else:
            self._invalid_fields.append(INTERFACE_TYPE_FIELD)

        if CONNECTION_CODE_FIELD in daq_dict:
            connection_code = daq_dict[CONNECTION_CODE_FIELD]
            if is_int_or_raise(connection_code):
                self._daq_params.connection_code = int(connection_code)
        else:
            self._invalid_fields.append(CONNECTION_CODE_FIELD)

    def _parse_ai_params(self):
        self._ai_params = AiParams()
        ai_dict = self._settings_dict[AI_FIELD]

        if RANGE_ID_FIELD in ai_dict:
            range_id = ai_dict[RANGE_ID_FIELD]
            if is_int_or_raise(range_id):
                self._ai_params.range_id = int(range_id)
        else:
            self._invalid_fields.append(RANGE_ID_FIELD)

        if LOW_CHANNEL_FIELD in ai_dict:
            low_channel = ai_dict[LOW_CHANNEL_FIELD]
            if is_int_or_raise(low_channel):
                self._ai_params.low_channel = int(low_channel)
        else:
            self._invalid_fields.append(LOW_CHANNEL_FIELD)

        if HIGH_CHANNEL_FIELD in ai_dict:
            high_channel = ai_dict[HIGH_CHANNEL_FIELD]
            if is_int_or_raise(high_channel):
                self._ai_params.high_channel = int(high_channel)
        else:
            self._invalid_fields.append(HIGH_CHANNEL_FIELD)

        if INPUT_MODE_FIELD in ai_dict:
            input_mode = ai_dict[INPUT_MODE_FIELD]
            if is_int_or_raise(input_mode):
                self._ai_params.input_mode = int(input_mode)
        else:
            self._invalid_fields.append(INPUT_MODE_FIELD)

        if SCAN_FLAGS_FIELD in ai_dict:
            scan_flags = ai_dict[SCAN_FLAGS_FIELD]
            if isinstance(scan_flags, list):
                self._ai_params.scan_flags = list_bitwise_or(scan_flags)
            elif is_int_or_raise(scan_flags):
                self._ai_params.scan_flags = int(scan_flags)
        else:
            self._invalid_fields.append(SCAN_FLAGS_FIELD)

    def _parse_ao_params(self):
        self._ao_params = AoParams()
        ao_dict = self._settings_dict[AO_FIELD]

        if RANGE_ID_FIELD in ao_dict:
            range_id = ao_dict[RANGE_ID_FIELD]
            if is_int_or_raise(range_id):
                self._ao_params.range_id = int(range_id)
        else:
            self._invalid_fields.append(RANGE_ID_FIELD)

        if LOW_CHANNEL_FIELD in ao_dict:
            low_channel = ao_dict[LOW_CHANNEL_FIELD]
            if is_int_or_raise(low_channel):
                self._ao_params.low_channel = int(low_channel)
        else:
            self._invalid_fields.append(LOW_CHANNEL_FIELD)

        if HIGH_CHANNEL_FIELD in ao_dict:
            high_channel = ao_dict[HIGH_CHANNEL_FIELD]
            if is_int_or_raise(high_channel):
                self._ao_params.high_channel = int(high_channel)
        else:
            self._invalid_fields.append(HIGH_CHANNEL_FIELD)

        if AMPLITUDE_FIELD in ao_dict:
            amplitude = ao_dict[AMPLITUDE_FIELD]
            if is_int_or_raise(amplitude):
                self._ao_params.amplitude = int(amplitude)
        else:
            self._invalid_fields.append(AMPLITUDE_FIELD)

        if OFFSET_FIELD in ao_dict:
            offset = ao_dict[OFFSET_FIELD]
            if is_int_or_raise(offset):
                self._ao_params.offset = int(offset)
        else:
            self._invalid_fields.append(OFFSET_FIELD)

        if PERIOD_FIELD in ao_dict:
            period = ao_dict[PERIOD_FIELD]
            if is_int_or_raise(period):
                self._ao_params.period = int(period)
        else:
            self._invalid_fields.append(PERIOD_FIELD)

        if SCAN_FLAGS_FIELD in ao_dict:
            scan_flags = ao_dict[SCAN_FLAGS_FIELD]
            if isinstance(scan_flags, list):
                self._ao_params.scan_flags = list_bitwise_or(scan_flags)
            elif is_int_or_raise(scan_flags):
                self._ao_params.scan_flags = int(scan_flags)
        else:
            self._invalid_fields.append(SCAN_FLAGS_FIELD)

    def _check_invalid_fields(self):
        if self._invalid_fields:
            invalid_fields_str = ", ".join(self._invalid_fields)
            raise ValueError("No fields found in the settings file: {}.".format(invalid_fields_str))


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
