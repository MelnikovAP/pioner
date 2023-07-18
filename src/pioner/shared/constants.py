from os import path

# Common constants
# =================================================================================
MAX_SCAN_SAMPLE_RATE = 1000000
JSON_EXTENSION = "json"
H5_EXTENSION = "h5"

ROOT_PATH = path.dirname(path.dirname(path.realpath(__file__)))

# Settings constants
# =================================================================================
SETTINGS_FOLDER = "settings"

SETTINGS_FOLDER_REL_PATH = path.join("./", SETTINGS_FOLDER)     #./ for user settings files to use folder from where package was called
SETTINGS_FILE = "settings.json"
SETTINGS_FILE_REL_PATH = path.join(SETTINGS_FOLDER_REL_PATH, SETTINGS_FILE)

DEFAULT_SETTINGS_FOLDER_REL_PATH = path.join(ROOT_PATH, SETTINGS_FOLDER)    # use package installation directory
DEFAULT_SETTINGS_FILE = "default_settings.json"
DEFAULT_SETTINGS_FILE_REL_PATH = path.join(DEFAULT_SETTINGS_FOLDER_REL_PATH, DEFAULT_SETTINGS_FILE)

# JSON fields backend
DAQ_SETTINGS_FIELD = "DAQ settings"

DAQ_FIELD = "DAQ"
AI_FIELD = "AI"
AO_FIELD = "AO"

INTERFACE_TYPE_FIELD = "InterfaceType"
CONNECTION_CODE_FIELD = "ConnectionCode"

RANGE_ID_FIELD = "RangeId"
LOW_CHANNEL_FIELD = "LowChannel"
HIGH_CHANNEL_FIELD = "HighChannel"
INPUT_MODE_FIELD = "InputMode"
SCAN_FLAGS_FIELD = "ScanFlags"

# JSON fields server
SERVER_SETTINGS_FIELD = "Server settings"

TANGO_FIELD = "Tango"
TANGO_HOST_FIELD = "Tango host"
DEVICE_PROXY_FIELD = "Device proxy"

HTTP_FIELD = "HTTP"
HTTP_HOST = "HTTP host"

# JSON fields experiment 
EXPERIMENT_SETTINGS_FIELD = "Experiment settings"

PATHS_FIELD = "Paths"
CALIB_PATH_FIELD = "Calibration path"
DATA_PATH_FIELD = "Data path"

SCAN_FIELD = "Scan"
SAMPLE_RATE_FIELD = "Sample rate"

MODULATION_FIELD = "Modulation"
FREQUENCY_FIELD = "Frequency"
AMPLITUDE_FIELD = "Amplitude"
OFFSET_FIELD = "Offset"

# Raw data constants
# =================================================================================
DATA_FOLDER = "data"
DATA_FOLDER_REL_PATH = path.join("./", DATA_FOLDER)
RAW_DATA_FOLDER = "raw_data"
RAW_DATA_FOLDER_REL_PATH = path.join(DATA_FOLDER_REL_PATH, RAW_DATA_FOLDER)
RAW_DATA_FILE = "raw_data.h5"
RAW_DATA_FILE_REL_PATH = path.join(RAW_DATA_FOLDER_REL_PATH, RAW_DATA_FILE)

RAW_DATA_BUFFER_FILE_PREFIX = "raw_data_buffer_"
RAW_DATA_BUFFER_FILE_FORMAT = "raw_data_buffer_{}.h5"
BUFFER_DUMMY_1 = "raw_data_dummy_1.h5"
BUFFER_DUMMY_2 = "raw_data_dummy_2.h5"

EXP_DATA_FILE = "exp_data.h5"
EXP_DATA_FILE_REL_PATH = path.join(DATA_FOLDER_REL_PATH, EXP_DATA_FILE)

# Logs constants
# =================================================================================
LOGS_FOLDER = "logs"
LOGS_FOLDER_REL_PATH = path.abspath(path.join("./", LOGS_FOLDER))
NANOCONTROL_LOG_FILE = "nanocontrol.log"
NANOCONTROL_LOG_FILE_REL_PATH = path.join(LOGS_FOLDER_REL_PATH, NANOCONTROL_LOG_FILE)

# Calibration constants
# =================================================================================
CALIBRATION_FILE = "calibration.json"
CALIBRATION_FILE_REL_PATH = path.join(SETTINGS_FOLDER_REL_PATH, CALIBRATION_FILE)
DEFAULT_CALIBRATION_FILE = "default_calibration.json"
DEFAULT_CALIBRATION_FILE_REL_PATH = path.join(DEFAULT_SETTINGS_FOLDER_REL_PATH, DEFAULT_CALIBRATION_FILE)

INFO_FIELD = "Info"

CALIBRATION_COEFFS_FIELD = "Calibration coeff"
U_TPL_FIELD = "Utpl"
T_TPL_FIELD = "Ttpl"
T_HTR_FIELD = "Thtr"
T_HTRD_FIELD = "Thtrd"
U_HTR_FIELD = "Uhtr"
I_HTR_FIELD = "Ihtr"
T_HEATER_FIELD = "Theater"
AMPLITUDE_CORRECTION_FIELD = "Amplitude correction"
R_HEATER_FIELD = "R heater"
R_GUARD_FIELD = "R guard"
HEATER_SAFE_VOLTAGE_FIELD = "Heater safe voltage"
CORR_FIELD = "corr"
# =================================================================================


if __name__=="__main__":
    print(ROOT_PATH)