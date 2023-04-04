import json
from constants import *


class mainParams:
    def __init__(self):
        self.tango_host = "lid13ctrl1.esrf.fr:20000"
        self.device_proxy = "ID13/NanoControl/1"

        self.http_host = "http://id13tmp0:8000/"

        self.calib_path = "./settings/calibration.json"
        self.data_path = "./data/"

        self.sample_rate = 20000

        self.modulation_frequency = 37.5
        self.modulation_amplitude = 0.1
        self.modulation_offset = 0.3

    def __str__(self):
        return str(vars(self))

    def get_dict(self):
        params_dict = {}
        params_dict[SETTINGS_FIELD] = {}
        params_dict[SETTINGS_FIELD][TANGO_FIELD] = {
            TANGO_HOST_FIELD: self.tango_host,
            DEVICE_PROXY_FIELD: self.device_proxy
            }
        params_dict[SETTINGS_FIELD][HTTP_FIELD] = {
            HTTP_HOST: self.http_host
            }
        params_dict[SETTINGS_FIELD][PATHS_FIELD] = {
            CALIB_PATH_FIELD: self.calib_path,
            DATA_PATH_FIELD: self.data_path
            }
        params_dict[SETTINGS_FIELD][SCAN_FIELD] = {
            SAMPLE_RATE_FIELD: self.sample_rate
            }
        params_dict[SETTINGS_FIELD][MODULATION_FIELD] ={
            FREQUENCY_FIELD: self.modulation_frequency,
            AMPLITUDE_FIELD: self.modulation_amplitude,
            OFFSET_FIELD: self.modulation_offset
            }

        return params_dict

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


class Settings(mainParams):
    """Parses configuration file with all necessary acquisition parameters."""

    def __init__(self, path: str):
        """Initializes dictionary and checks that all needed fields exist.

        After correct parsing it is possible to obtain ???? AM: add description.

        Args:
            path: A string path to JSON file.

        Raises:
            ValueError if any field doesn't exist.
        """
        self._json_dict = JsonReader(path).json()
        if SETTINGS_FIELD not in self._json_dict:
            raise ValueError("No '{}' field found in the settings file.".format(SETTINGS_FIELD))
        else:
            self._settings_dict = self._json_dict[SETTINGS_FIELD]
            for field in [TANGO_FIELD, HTTP_FIELD, PATHS_FIELD, SCAN_FIELD, MODULATION_FIELD]:
                if field not in self._settings_dict:
                    raise ValueError("No '{}' field found in the settings file.".format(field))
        self._invalid_fields = []
        # only in that order
        self.parse_params()
        self.check_invalid_fields()

    def parse_params(self):
        """Parses all necessary parameters and fills instance."""

        for field in [TANGO_HOST_FIELD, DEVICE_PROXY_FIELD]:
            if field not in self._settings_dict[TANGO_FIELD] or \
                not isinstance(self._settings_dict[TANGO_FIELD][field], str):
                self._invalid_fields.append(field)

        for field in [HTTP_HOST]:
            if field not in self._settings_dict[HTTP_FIELD] or \
                not isinstance(self._settings_dict[HTTP_FIELD][field], str):
                self._invalid_fields.append(field)

        for field in [CALIB_PATH_FIELD, DATA_PATH_FIELD]:
            if field not in self._settings_dict[PATHS_FIELD] or \
                not isinstance(self._settings_dict[PATHS_FIELD][field], str):
                self._invalid_fields.append(field)

        for field in [SAMPLE_RATE_FIELD]:
            if field not in self._settings_dict[SCAN_FIELD] or \
                not isinstance(self._settings_dict[SCAN_FIELD][field], int):
                self._invalid_fields.append(field)
        
        for field in [FREQUENCY_FIELD, AMPLITUDE_FIELD, OFFSET_FIELD]:
            if field not in self._settings_dict[MODULATION_FIELD] or \
                not isinstance(self._settings_dict[MODULATION_FIELD][field], float):
                self._invalid_fields.append(field)
            

        self.tango_host = self._settings_dict[TANGO_FIELD][TANGO_HOST_FIELD]
        self.device_proxy = self._settings_dict[TANGO_FIELD][DEVICE_PROXY_FIELD]

        self.http_host = self._settings_dict[HTTP_FIELD][HTTP_HOST]

        self.calib_path = self._settings_dict[PATHS_FIELD][CALIB_PATH_FIELD]
        self.data_path = self._settings_dict[PATHS_FIELD][DATA_PATH_FIELD]

        self.sample_rate = self._settings_dict[SCAN_FIELD][SAMPLE_RATE_FIELD]

        self.modulation_frequency = self._settings_dict[MODULATION_FIELD][FREQUENCY_FIELD]
        self.modulation_amplitude = self._settings_dict[MODULATION_FIELD][AMPLITUDE_FIELD]
        self.modulation_offset = self._settings_dict[MODULATION_FIELD][OFFSET_FIELD]

    def check_invalid_fields(self):
        """Raises ValueError if at least one required field is missing in the settings."""
        if self._invalid_fields:
            invalid_fields_str = ", ".join(self._invalid_fields)
            raise ValueError("Wrong or missing inputs in the settings file: {}.".format(invalid_fields_str))


if __name__ == '__main__':
    _path = "./settings/.settings.json"
    settings = Settings(_path)
    print(settings.sample_rate)