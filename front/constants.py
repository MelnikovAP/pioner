import os

# Common constants
# =================================================================================
MAX_SCAN_SAMPLE_RATE = 1000000
JSON_EXTENSION = "json"
H5_EXTENSION = "h5"


# Settings constants
# =================================================================================
SETTINGS_FOLDER = "settings"
SETTINGS_FOLDER_REL_PATH = os.path.join(".", SETTINGS_FOLDER)
SETTINGS_FILE = ".settings.json"
SETTINGS_FILE_REL_PATH = os.path.join(SETTINGS_FOLDER_REL_PATH, SETTINGS_FILE)  # TODO: use

# JSON fields
SETTINGS_FIELD = "Settings"

TANGO_FIELD = "TANGO"
TANGO_HOST_FIELD = "TANGO_HOST"
DEVICE_PROXY_FIELD = "DEVICE_PROXY"

HTTP_FIELD = "HTTP"
HTTP_HOST = "HTTP_HOST"

PATHS_FIELD = "PATHS"
CALIB_PATH_FIELD = "CALIB_PATH"
DATA_PATH_FIELD = "DATA_PATH"

SCAN_FIELD = "SCAN"
SAMPLE_RATE_FIELD = "SAMPLE_RATE"

MODULATION_FIELD = "MODULATION"
FREQUENCY_FIELD = "FREQUENCY"
AMPLITUDE_FIELD = "AMPLITUDE"
OFFSET_FIELD = "OFFSET"

# Calibration constants
# =================================================================================

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