from messageWindows import *

# AM: check later if this class is indeed nessesary. Now almost all
# buttons are disabled after no-hardware mode switched on.

class virtualDevice:
    def __init__(self):
        self.error_text = "Impossible action.\nNo-hardware mode is active"
        
    def disconnect(self):
        pass

    def load_calibration(self):
        ErrorWindow(self.error_text)
    
    def apply_calibration(self):
        ErrorWindow(self.error_text)

    def apply_default_calibration(self):
        ErrorWindow(self.error_text)

    def get_current_calibration(self):
        ErrorWindow(self.error_text)

    def set_fh_time_profile(self):
        ErrorWindow(self.error_text)

    def set_fh_temp_profile(self):
        ErrorWindow(self.error_text)

    def arm_fast_heat(self):
        ErrorWindow(self.error_text)

    def run_fast_heat(self):
        ErrorWindow(self.error_text)