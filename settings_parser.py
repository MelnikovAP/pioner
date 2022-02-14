from settings_constants import *
from daq_params import DaqParams
from scan_params import ScanParams
from ai_params import AiParams
from ao_params import AoParams

from settings import Settings
import os


class SettingsParser:
    def __init__(self, path: str):
        json_dict = Settings(path).get_json()
        if not SETTINGS_FIELD in json_dict:
            raise ValueError("No '{}' field found in the settings file.".format(SETTINGS_FIELD))
        else:
            self._settings_dict = json_dict[SETTINGS_FIELD]
            for field in [DAQ_FIELD, SCAN_FIELD, AI_FIELD, AO_FIELD]:
                if not field in self._settings_dict:
                    raise ValueError("No '{}' field found in the settings file.".format(field))
        self._parse_daq_params()
        self._parse_scan_params()
        self._parse_ai_params()
        self._parse_ao_params()

    def get_daq_params(self) -> DaqParams:
        return self._daq_params

    def get_scan_params(self) -> ScanParams:
        return self._scan_params

    def get_ai_params(self) -> AiParams:
        return self._ai_params

    def get_ao_params(self) -> AoParams:
        return self._ao_params

    def _parse_daq_params(self):
        self._daq_params = DaqParams()
        daq_dict = self._settings_dict[DAQ_FIELD]
        if INTERFACE_TYPE_FIELD in daq_dict:
            interface_types = daq_dict[INTERFACE_TYPE_FIELD]
            if isinstance(interface_types, list):
                for interface_type in interface_types:
                    if isinstance(interface_type, str) and interface_type.isdigit():
                        self._scan_params.interface_type = interface_type  # TODO: check
            elif isinstance(interface_types, str) and interface_types.isdigit():
                self._daq_params.interface_type = int(interface_types)
        else:
            raise ValueError("No '{}' field found in the settings file.".format(INTERFACE_TYPE_FIELD))

        if CONNECTION_CODE_FIELD in daq_dict:
            connection_code = daq_dict[CONNECTION_CODE_FIELD]
            if isinstance(connection_code, str) and connection_code.isdigit():
                self._daq_params.connection_code = int(connection_code)

    def _parse_scan_params(self):
        self._scan_params = ScanParams()
        scan_dict = self._settings_dict[SCAN_FIELD]
        if SAMPLE_RATE_FIELD in scan_dict:
            sample_rate = scan_dict[SAMPLE_RATE_FIELD]
            if isinstance(sample_rate, str) and sample_rate.isdigit():
                self._scan_params.sample_rate = min(int(sample_rate), MAX_SCAN_SAMPLE_RATE)

        if CHANNEL_COUNT_FIELD in scan_dict:
            channel_count = scan_dict[CHANNEL_COUNT_FIELD]
            if isinstance(sample_rate, str) and sample_rate.isdigit():
                self._scan_params.channel_count = int(channel_count)

        if OPTIONS_FIELD in scan_dict:
            options = scan_dict[OPTIONS_FIELD]
            if isinstance(options, list):
                for option in options:
                    if isinstance(option, str) and option.isdigit():
                        self._scan_params.options = option  # TODO: check
            elif isinstance(options, str) and options.isdigit():
                self._scan_params.options = options

    def _parse_ai_params(self):
        self._ai_params = AiParams()
        ai_dict = self._settings_dict[AI_FIELD]

        if RANGE_ID_FIELD in ai_dict:
            range_id = ai_dict[RANGE_ID_FIELD]
            if isinstance(range_id, str) and range_id.isdigit():
                self._ai_params.range_id = range_id

        if LOW_CHANNEL_FIELD in ai_dict:
            low_channel = ai_dict[LOW_CHANNEL_FIELD]
            if isinstance(low_channel, str) and low_channel.isdigit():
                self._ai_params.low_channel = low_channel

        if HIGH_CHANNEL_FIELD in ai_dict:
            high_channel = ai_dict[HIGH_CHANNEL_FIELD]
            if isinstance(high_channel, str) and high_channel.isdigit():
                self._ai_params.high_channel = high_channel

        if INPUT_MODE_FIELD in ai_dict:
            input_mode = ai_dict[INPUT_MODE_FIELD]
            if isinstance(input_mode, str) and input_mode.isdigit():
                self._ai_params.input_mode = input_mode

        if SCAN_FLAGS_FIELD in ai_dict:
            scan_flags = ai_dict[SCAN_FLAGS_FIELD]
            if isinstance(scan_flags, list):
                for scan_flag in scan_flags:
                    if isinstance(scan_flag, str) and scan_flag.isdigit():
                        self._scan_params.scan_flags = scan_flag  # TODO: check
            elif isinstance(scan_flags, str) and scan_flags.isdigit():
                self._ai_params.scan_flags = scan_flags

    def _parse_ao_params(self):
        self._ao_params = AoParams()
        ao_dict = self._settings_dict[AO_FIELD]

        if RANGE_ID_FIELD in ao_dict:
            range_id = ao_dict[RANGE_ID_FIELD]
            if isinstance(range_id, str) and range_id.isdigit():
                self._ao_params.range_id = range_id

        if LOW_CHANNEL_FIELD in ao_dict:
            low_channel = ao_dict[LOW_CHANNEL_FIELD]
            if isinstance(low_channel, str) and low_channel.isdigit():
                self._ao_params.low_channel = low_channel

        if HIGH_CHANNEL_FIELD in ao_dict:
            high_channel = ao_dict[HIGH_CHANNEL_FIELD]
            if isinstance(high_channel, str) and high_channel.isdigit():
                self._ao_params.high_channel = high_channel

        if SCAN_FLAGS_FIELD in ao_dict:
            scan_flags = ao_dict[SCAN_FLAGS_FIELD]
            if isinstance(scan_flags, list):
                for scan_flag in scan_flags:
                    if isinstance(scan_flag, str) and scan_flag.isdigit():
                        self._scan_params.scan_flags = scan_flag  # TODO: check
            elif isinstance(scan_flags, str) and scan_flags.isdigit():
                self._ao_params.scan_flags = scan_flags





if __name__ == '__main__':
    try:
    	path = "settings.json"
    	parser = SettingsParser(path)

    except BaseException as e:
        print(e)
