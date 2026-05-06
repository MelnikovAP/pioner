from pioner.front.messageWindows import *

# AM: check later if this class is indeed nessesary. Now almost all
# buttons are disabled after no-hardware mode switched on.


class virtualDevice:
    """Stand-in for the real Tango proxy in *no-hardware* GUI mode.

    Every method that would normally hit the device pops up an error window
    and returns without effect. Methods are kept in sync with
    :class:`pioner.back.nanocontrol_tango.NanoControl` so that the GUI can
    safely call any of them.
    """

    def __init__(self):
        self.error_text = "Impossible action.\nNo-hardware mode is active"

    def _refuse(self, *_args, **_kwargs):
        ErrorWindow(self.error_text)

    # ``disconnect`` is the only method that must succeed silently so the GUI
    # close-down path keeps working in no-hardware mode.
    def disconnect(self):
        pass

    # All real Tango commands are mapped to ``_refuse``.
    load_calibration = _refuse
    apply_calibration = _refuse
    apply_default_calibration = _refuse
    get_current_calibration = _refuse
    get_sample_rate = _refuse
    set_sample_scan_rate = _refuse
    reset_sample_scan_rate = _refuse
    set_connection = _refuse
    select_mode = _refuse
    arm = _refuse
    run = _refuse
    arm_fast_heat = _refuse
    run_fast_heat = _refuse
    arm_iso_mode = _refuse
    run_iso_mode = _refuse