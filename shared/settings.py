import json
import sys
sys.path.append('./')

from back.ai_device import AiParams
from back.ao_device import AoParams
from back.daq_device import DaqParams
from shared.utils import is_int_or_raise, list_bitwise_or
from shared.constants import *


class JsonReader:
    """Reads a JSON configuration file."""

    def __init__(self, path: str):
        """Initializes dictionary.

        Args:
            path: A string path to JSON file.

        Raises:
            ValueError if file doesn't exist or has invalid extension or is empty.
        """
        self._json = dict()
        if not os.path.exists(path):
            raise ValueError("Settings file doesn't exist.")
        if not os.path.splitext(path)[-1] != JSON_EXTENSION:
            raise ValueError("Settings file doesn't have '{}' extension.".format(JSON_EXTENSION))
        with open(path, 'r') as f:
            self._json = json.load(f)
        if not self._json:
            raise ValueError("Empty settings file defined.")

    def json(self):
        """Provides access to the read dictionary."""
        return self._json

class BackSettings:
    """Parses configuration file with all necessary acquisition parameters."""

    def __init__(self, path: str):
        """Initializes dictionary and checks that all needed fields exist.

        After correct parsing it is possible to obtain DaqParams, AiParams and AoParams.

        Args:
            path: A string path to JSON file.

        Raises:
            ValueError if any field doesn't exist.
        """
        json_dict = JsonReader(path).json()
        if DAQ_SETTINGS_FIELD not in json_dict:
            raise ValueError("No '{}' field found in the settings file.".format(DAQ_SETTINGS_FIELD))
        else:
            self._daq_settings_dict = json_dict[DAQ_SETTINGS_FIELD]
            for field in [DAQ_FIELD, AI_FIELD, AO_FIELD]:
                if field not in self._daq_settings_dict:
                    raise ValueError("No '{}' field found in the settings file.".format(field))
        
        if EXPERIMENT_SETTINGS_FIELD not in json_dict:
            raise ValueError("No '{}' field found in the settings file.".format(EXPERIMENT_SETTINGS_FIELD))
        else:
            self._exp_settings_dict = json_dict[EXPERIMENT_SETTINGS_FIELD]
            for field in [PATHS_FIELD, SCAN_FIELD, MODULATION_FIELD]:
                if field not in self._exp_settings_dict:
                    raise ValueError("No '{}' field found in the settings file.".format(field))

        self._invalid_fields = []
        # only in that order
        self.parse_daq_params()
        self.parse_ai_params()
        self.parse_ao_params()
        self.check_invalid_fields()

    def parse_daq_params(self):
        """Parses all necessary DAQ parameters and fills DaqParams instance."""
        self.daq_params = DaqParams()
        daq_dict = self._daq_settings_dict[DAQ_FIELD]

        if INTERFACE_TYPE_FIELD in daq_dict:
            interface_types = daq_dict[INTERFACE_TYPE_FIELD]
            if isinstance(interface_types, list):
                self.daq_params.interface_type = list_bitwise_or(interface_types)
            elif is_int_or_raise(interface_types):
                self.daq_params.interface_type = int(interface_types)
        else:
            self._invalid_fields.append(INTERFACE_TYPE_FIELD)

        if CONNECTION_CODE_FIELD in daq_dict:
            connection_code = daq_dict[CONNECTION_CODE_FIELD]
            if is_int_or_raise(connection_code):
                self.daq_params.connection_code = int(connection_code)
        else:
            self._invalid_fields.append(CONNECTION_CODE_FIELD)

    def parse_ai_params(self):
        """Parses all necessary analog-input parameters and fills AiParams instance."""
        self.ai_params = AiParams()
        ai_dict = self._daq_settings_dict[AI_FIELD]
        scan_dict = self._exp_settings_dict[SCAN_FIELD]

        if SAMPLE_RATE_FIELD in scan_dict:
            sample_rate = scan_dict[SAMPLE_RATE_FIELD]
            if is_int_or_raise(sample_rate):
                self.ai_params.sample_rate = int(sample_rate)
        else:
            if SAMPLE_RATE_FIELD not in self._invalid_fields:
                self._invalid_fields.append(SAMPLE_RATE_FIELD)

        if RANGE_ID_FIELD in ai_dict:
            range_id = ai_dict[RANGE_ID_FIELD]
            if is_int_or_raise(range_id):
                self.ai_params.range_id = int(range_id)
        else:
            self._invalid_fields.append(RANGE_ID_FIELD)

        if LOW_CHANNEL_FIELD in ai_dict:
            low_channel = ai_dict[LOW_CHANNEL_FIELD]
            if is_int_or_raise(low_channel):
                self.ai_params.low_channel = int(low_channel)
        else:
            self._invalid_fields.append(LOW_CHANNEL_FIELD)

        if HIGH_CHANNEL_FIELD in ai_dict:
            high_channel = ai_dict[HIGH_CHANNEL_FIELD]
            if is_int_or_raise(high_channel):
                self.ai_params.high_channel = int(high_channel)
        else:
            self._invalid_fields.append(HIGH_CHANNEL_FIELD)

        if INPUT_MODE_FIELD in ai_dict:
            input_mode = ai_dict[INPUT_MODE_FIELD]
            if is_int_or_raise(input_mode):
                self.ai_params.input_mode = int(input_mode)
        else:
            self._invalid_fields.append(INPUT_MODE_FIELD)

        if SCAN_FLAGS_FIELD in ai_dict:
            scan_flags = ai_dict[SCAN_FLAGS_FIELD]
            if isinstance(scan_flags, list):
                self.ai_params.scan_flags = list_bitwise_or(scan_flags)
            elif is_int_or_raise(scan_flags):
                self.ai_params.scan_flags = int(scan_flags)
        else:
            self._invalid_fields.append(SCAN_FLAGS_FIELD)

    def parse_ao_params(self):
        """Parses all necessary analog-output parameters and fills AoParams instance."""
        self.ao_params = AoParams()
        ao_dict = self._daq_settings_dict[AO_FIELD]
        scan_dict = self._exp_settings_dict[SCAN_FIELD]

        if SAMPLE_RATE_FIELD in scan_dict:
            sample_rate = scan_dict[SAMPLE_RATE_FIELD]
            if is_int_or_raise(sample_rate):
                self.ao_params.sample_rate = int(sample_rate)
        else:
            if SAMPLE_RATE_FIELD not in self._invalid_fields:
                self._invalid_fields.append(SAMPLE_RATE_FIELD)

        if RANGE_ID_FIELD in ao_dict:
            range_id = ao_dict[RANGE_ID_FIELD]
            if is_int_or_raise(range_id):
                self.ao_params.range_id = int(range_id)
        else:
            self._invalid_fields.append(RANGE_ID_FIELD)

        if LOW_CHANNEL_FIELD in ao_dict:
            low_channel = ao_dict[LOW_CHANNEL_FIELD]
            if is_int_or_raise(low_channel):
                self.ao_params.low_channel = int(low_channel)
        else:
            self._invalid_fields.append(LOW_CHANNEL_FIELD)

        if HIGH_CHANNEL_FIELD in ao_dict:
            high_channel = ao_dict[HIGH_CHANNEL_FIELD]
            if is_int_or_raise(high_channel):
                self.ao_params.high_channel = int(high_channel)
        else:
            self._invalid_fields.append(HIGH_CHANNEL_FIELD)

        if SCAN_FLAGS_FIELD in ao_dict:
            scan_flags = ao_dict[SCAN_FLAGS_FIELD]
            if isinstance(scan_flags, list):
                self.ao_params.scan_flags = list_bitwise_or(scan_flags)
            elif is_int_or_raise(scan_flags):
                self.ao_params.scan_flags = int(scan_flags)
        else:
            self._invalid_fields.append(SCAN_FLAGS_FIELD)

    def check_invalid_fields(self):
        """Raises ValueError if at least one required field is missing in the settings."""
        if self._invalid_fields:
            invalid_fields_str = ", ".join(self._invalid_fields)
            raise ValueError("No fields found in the settings file: {}.".format(invalid_fields_str))

    def get_str(self):
        _daq_params = str(self.daq_params)
        _ai_params = str(self.ai_params)
        _ao_params = str(self.ao_params)
        settings_dict = str({"DAQ":_daq_params, "AI":_ai_params, "AO":_ao_params})
        settings_dict = settings_dict.replace("\'", "\"")               # need because json.loads does not recognie " ' "
        
        return settings_dict

class FrontSettings:
    """Parses configuration file with all necessary acquisition parameters."""

    def __init__(self, path: str):
        """Initializes dictionary and checks that all needed fields exist.

        After correct parsing it is possible to obtain ???? AM: add description.

        Args:
            path: A string path to JSON file.

        Raises:
            ValueError if any field doesn't exist.
        """

        json_dict = JsonReader(path).json()

        if SERVER_SETTINGS_FIELD not in json_dict:
            raise ValueError("No '{}' field found in the settings file.".format(SERVER_SETTINGS_FIELD))
        else:
            self._server_settings_dict = json_dict[SERVER_SETTINGS_FIELD]
            for field in [TANGO_FIELD, HTTP_FIELD]:
                if field not in self._server_settings_dict:
                    raise ValueError("No '{}' field found in the settings file.".format(field))
        
        if EXPERIMENT_SETTINGS_FIELD not in json_dict:
            raise ValueError("No '{}' field found in the settings file.".format(EXPERIMENT_SETTINGS_FIELD))
        else:
            self._exp_settings_dict = json_dict[EXPERIMENT_SETTINGS_FIELD]
            for field in [PATHS_FIELD, SCAN_FIELD, MODULATION_FIELD]:
                if field not in self._exp_settings_dict:
                    raise ValueError("No '{}' field found in the settings file.".format(field))


        self._invalid_fields = []
        # only in that order
        self.parse_server_params()
        self.parse_experiment_params()
        self.check_invalid_fields()
        self.set_server_settings()
        self.set_exp_settings()

    def parse_server_params(self):
        for field in [TANGO_HOST_FIELD, DEVICE_PROXY_FIELD]:
            if field not in self._server_settings_dict[TANGO_FIELD] or \
                not isinstance(self._server_settings_dict[TANGO_FIELD][field], str):
                self._invalid_fields.append(field)

        for field in [HTTP_HOST]:
            if field not in self._server_settings_dict[HTTP_FIELD] or \
                not isinstance(self._server_settings_dict[HTTP_FIELD][field], str):
                self._invalid_fields.append(field)

    def parse_experiment_params(self):
        for field in [CALIB_PATH_FIELD, DATA_PATH_FIELD]:
            if field not in self._exp_settings_dict[PATHS_FIELD] or \
                not isinstance(self._exp_settings_dict[PATHS_FIELD][field], str):
                self._invalid_fields.append(field)

        for field in [SAMPLE_RATE_FIELD]:
            if field not in self._exp_settings_dict[SCAN_FIELD] or \
                not isinstance(self._exp_settings_dict[SCAN_FIELD][field], int):
                self._invalid_fields.append(field)
        
        for field in [FREQUENCY_FIELD, AMPLITUDE_FIELD, OFFSET_FIELD]:
            if field not in self._exp_settings_dict[MODULATION_FIELD] or \
                not isinstance(self._exp_settings_dict[MODULATION_FIELD][field], float):
                self._invalid_fields.append(field)

    def set_server_settings(self):
        if not self._invalid_fields:
            self.tango_host = self._server_settings_dict[TANGO_FIELD][TANGO_HOST_FIELD]
            self.device_proxy = self._server_settings_dict[TANGO_FIELD][DEVICE_PROXY_FIELD]
            self.http_host = self._server_settings_dict[HTTP_FIELD][HTTP_HOST]

    def get_server_settings(self):
        return {TANGO_FIELD: {
                    TANGO_HOST_FIELD: self.tango_host,
                    DEVICE_PROXY_FIELD: self.device_proxy
                    },
                HTTP_FIELD:{
                    HTTP_HOST: self.http_host
                    }
                }

    def set_exp_settings(self):
        if not self._invalid_fields:
            self.calib_path = os.path.abspath(self._exp_settings_dict[PATHS_FIELD][CALIB_PATH_FIELD])
            self.data_path = os.path.abspath(self._exp_settings_dict[PATHS_FIELD][DATA_PATH_FIELD])
            self.sample_rate = self._exp_settings_dict[SCAN_FIELD][SAMPLE_RATE_FIELD]
            self.modulation_frequency = self._exp_settings_dict[MODULATION_FIELD][FREQUENCY_FIELD]
            self.modulation_amplitude = self._exp_settings_dict[MODULATION_FIELD][AMPLITUDE_FIELD]
            self.modulation_offset = self._exp_settings_dict[MODULATION_FIELD][OFFSET_FIELD]

    def get_exp_settings(self):
        return {PATHS_FIELD: {
                    CALIB_PATH_FIELD: self.calib_path,
                    DATA_PATH_FIELD: self.data_path
                    },
                SCAN_FIELD:{
                    SAMPLE_RATE_FIELD: self.sample_rate
                    },
                MODULATION_FIELD: {
                    FREQUENCY_FIELD: self.modulation_frequency,
                    AMPLITUDE_FIELD: self.modulation_amplitude,
                    OFFSET_FIELD: self.modulation_offset
                    },
                }

    def check_invalid_fields(self):
        """Raises ValueError if at least one required field is missing in the settings."""
        if self._invalid_fields:
            invalid_fields_str = ", ".join(self._invalid_fields)
            raise ValueError("Wrong or missing inputs in the settings file: {}.".format(invalid_fields_str))

if __name__ == '__main__':

    _path = SETTINGS_FILE_REL_PATH
    # settings = BackSettings(_path)
    settings = FrontSettings(_path)

    # print(settings.get_str())
    print(settings.data_path)

