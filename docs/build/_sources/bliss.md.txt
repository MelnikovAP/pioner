# Script to operate from BLISS

```
import tango
import socket
import requests
from silx.gui import qt
from silx.gui.plot import Plot1D, PlotWindow
from silx.gui import icons
import os
import json
import time

################################################
## Setting the paths
nanocontrol_session_path = SCAN_SAVING.base_path + SCAN_SAVING.proposal_dirname + '/' + \
                          SCAN_SAVING.beamline + '/' + SCAN_SAVING.proposal_session_name + '/'
nanocontrol_save_path = nanocontrol_session_path + 'nanocontrol/'
nanocontrol_settings_path = nanocontrol_save_path + 'settings/.settings.json'

nanocontrol_data_path = nanocontrol_save_path + 'data/'
nanocontrol_calibration_path = nanocontrol_save_path + 'settings/calibration.json'
################################################


class NanoControl():
    def __init__(self):
        self.reload_settings()

    def help(self):
        print('====================================================')
        print('=== Help is under developing. Please contact Melnikov Alexey:')
        print('=== alexey.melnikov@esrf.fr or 45-32')

    def reload_settings(self):
        with open(nanocontrol_settings_path, 'r') as f:
            settings = json.load(f)
            self._http_server_url = settings['Settings']['HTTP']['HTTP_HOST']
            self._device_proxy = settings['Settings']['TANGO']['DEVICE_PROXY']
            self._tango_host = settings['Settings']['TANGO']['TANGO_HOST']
            self._calib_path = settings['Settings']['PATHS']['CALIB_PATH']
            self._data_path = settings['Settings']['PATHS']['DATA_PATH']
            self._sample_rate = settings['Settings']['SCAN']['SAMPLE_RATE']
            self._modulation_frequency = settings['Settings']['MODULATION']['FREQUENCY']
            self._modulation_amplitude = settings['Settings']['MODULATION']['AMPLITUDE']
            self._modulation_offset = settings['Settings']['MODULATION']['OFFSET']
            self.show_settings()

    def show_settings(self):
        print('Setting was applied from file: {}'.format(nanocontrol_settings_path))
        print('====================================================')
        print('===================== Device =======================')
        print('=== Device TANGO proxy: {}'.format(self._device_proxy))
        print('=== Device TANGO host: {}'.format(self._tango_host))
        print('=== HTTP server: {}'.format(self._http_server_url))
        print('===================== Paths ========================')
        print('=== Calibration path: {}'.format(self._calib_path))
        print('=== Data path: {}'.format(self._data_path))
        print('================= Scan parameters ==================')
        print('=== Sample rate: {}'.format(self._sample_rate))
        print('=== Modulation frequency: {}'.format(self._modulation_frequency))
        print('=== Modulation amplitude: {}'.format(self._modulation_amplitude))
        print('=== Modulation offset: {}'.format(self._modulation_offset))


    ######################
    ## Connection methods
    def set_connection(self):
        print('=== Device TANGO proxy is: {}'.format(self._device_proxy))
        print('=== Device TANGO host is: {}'.format(self._tango_host))
        try:
            self._device = tango.DeviceProxy(self._device_proxy)
            self._device.set_timeout_millis(10000000)
            self._device.set_connection()
            print('=== Successfully connected')
        except:
            print('=== Unsuccessfull connection to device')

    def disconnect(self):
        self._device.disconnect()
        print('=== Successfully disconnected from device')

    #######################
    ## Calibration methods
    def apply_default_calibration(self):
        self._device.apply_default_calibration()
        print('=== Default device calibration was applied')

    def load_and_apply_calibration(self, calib_path: str):
        if os.path.exists(calib_path):
            with open(calib_path, 'r') as f:
                raw_calib = json.load(f)
                str_calib = json.dumps(raw_calib)
                self._device.load_calibration(str_calib)
                self._device.apply_calibration()
            print('=== Calibration was successfully applied from: {}'.format(calib_path))
            self.show_calibration_info()

    def show_calibration_info(self):
        calib_dict = json.loads(self._device.get_current_calibration[1][0]['value'])
        print('=== Current calibration info: {}'.format(calib_dict['comment']))

    #######################
    ## Scan methods
    def set_scan_sample_rate(self, sample_rate: int):
        self._device.set_sample_scan_rate(sample_rate)
        self.show_scan_sample_rate()

    def show_scan_sample_rate(self):
        sr = self._device.get_sample_rate[1][0]['value']
        print('=== Current sample rate is: {}'.format(sr))

    ########################
    ## Fast heating methods
    def arm_fast_heat(self, time_profile: list, temp_profile:list):
        self._device.set_fh_time_profile(time_profile)
        self._device.set_fh_temp_profile(temp_profile)
        self._device.arm_fast_heat()
        print('====================================================')
        self.show_calibration_info()
        print('====================================================')
        self.show_settings()
        print('====================================================')
        print("=== Heating program armed: ")
        print('\t', 'time', '\t', 'temp')
        for i, time_point in enumerate(time_profile):
            print('\t', time_point, '\t', temp_profile[i])

    def run_fast_heat(self):
        self._device.run_fast_heat()
        print('====================================================')
        print('=== Fast heating finised!')
        self._download_data()
        print('====================================================')
        print('=== Data files were saved to: {}'.format(nanocontrol_data_path))
        print('=== Files prefixes: {}'.format(SCAN_SAVING.collection_name + '_' + \
                                              SCAN_SAVING.dataset_name + '_'))

    def _download_data(self):
        URL = self._http_server_url+'data/exp_data.h5'
        response = requests.get(URL, verify=False)
        current_time = time.localtime()
        file_time = time.strftime("%H_%M", current_time)
        full_file_path = nanocontrol_data_path + \
                         SCAN_SAVING.collection_name + '_' + \
                         SCAN_SAVING.dataset_name + '_' + \
                         file_time + '_exp.h5'
        with open(full_file_path, 'wb') as f:
            f.write(response.content)

        URL = self._http_server_url+'data/raw_data/raw_data.h5'
        response = requests.get(URL, verify=False)
        full_file_path = nanocontrol_data_path + \
                         SCAN_SAVING.collection_name + '_' + \
                         SCAN_SAVING.dataset_name + '_' + \
                         file_time + '_raw.h5'
        with open(full_file_path, 'wb') as f:
            f.write(response.content)


def install_nanocontrol_to_session():
    if os.path.exists(nanocontrol_save_path):
        print('NanoControl GUI was already set up for this session!')
    else:
        os.system('git clone https://github.com/MelnikovAP/nanocal_front.git {}'.format(nanocontrol_save_path))

        with open(nanocontrol_settings_path, 'r+') as f:
            settings = json.load(f)
            settings['Settings']['PATHS']['CALIB_PATH'] = nanocontrol_calibration_path
            settings['Settings']['PATHS']['DATA_PATH'] = nanocontrol_data_path
            if not os.path.exists(nanocontrol_data_path):
                os.system('mkdir {}'.format(nanocontrol_data_path))
            f.seek(0)
            json.dump(settings, f, separators=(',', ': '), indent=4)
    print('====================================================')
    print('NanoControl GUI was installed in: {}'.format(nanocontrol_save_path))
    print('Default folder to save nanocontrol data is: {}'.format(nanocontrol_data_path))
    print('Paths and settings could be changed by modifying {}'.format(nanocontrol_settings_path))



install_nanocontrol_to_session()
nanocontrol = NanoControl()

```