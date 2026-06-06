"""Quick smoke test for the back-end pipeline using the mock DAQ.

Run this as ``python -m pioner.back.debug`` to exercise all three modes
end-to-end without any real hardware. It is intentionally short -- the real
test suite lives in ``tests/`` and is run with ``pytest``.
"""

from __future__ import annotations

import logging

from pioner.shared.calibration import Calibration
from pioner.shared.constants import DEFAULT_SETTINGS_FILE_REL_PATH
from pioner.shared.settings import BackSettings
from pioner.back.daq_device import DaqDeviceHandler
from pioner.back.modes import create_mode

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _use_mode_rate(settings: BackSettings, mode: str) -> None:
    """Switch the active AI/AO rate to ``mode``'s configured value (P1-31).

    Mirrors what ``LocalDeviceController.arm`` does for the GUI path; here the
    smoke test drives modes directly, so apply the per-mode rate by hand.
    """
    rate = settings.sample_rate_by_mode[mode]
    settings.ai_params.sample_rate = rate
    settings.ao_params.sample_rate = rate


def main() -> None:
    settings = BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH)
    calibration = Calibration()
    daq = DaqDeviceHandler(settings.daq_params)
    daq.try_connect()
    try:
        # Fast: 1 second triangle on ch1, 0.1 V on ch0, 5 V on ch2.
        fast_programs = {
            "ch0": {"time": [0, 1000], "volt": [0.1, 0.1]},
            "ch1": {"time": [0, 500, 1000], "volt": [0, 1, 0]},
            "ch2": {"time": [0, 1000], "volt": [5, 5]},
        }
        _use_mode_rate(settings, "fast")
        mode = create_mode("fast", daq, settings, calibration, fast_programs)
        mode.arm()
        df = mode.run()
        print(f"Fast mode produced {len(df)} samples; columns: {list(df.columns)}")

        # Slow: 2 second 0->1 V ramp with AC modulation.
        slow_programs = {
            "ch0": {"time": [0, 2000], "volt": [0.1, 0.1]},
            "ch1": {"time": [0, 2000], "volt": [0, 1]},
        }
        _use_mode_rate(settings, "slow")
        mode = create_mode("slow", daq, settings, calibration, slow_programs)
        mode.arm()
        df = mode.run()
        print(
            f"Slow mode: {len(df)} samples, lock-in columns present: "
            f"{[c for c in df.columns if c.startswith('temp-hr_')]}"
        )

        # Iso: hold 0.5 V on ch1 with AC modulation for 1 s.
        iso_programs = {
            "ch1": {"volt": 0.5},
        }
        from pioner.back.iso_mode import IsoMode

        _use_mode_rate(settings, "iso")
        iso = IsoMode(daq, settings, iso_programs, calibration, duration_seconds=1)
        iso.arm()
        df = iso.run(do_ai=True, duration_seconds=1.0)
        if df is not None:
            print(f"Iso mode: {len(df)} samples")
    finally:
        daq.disconnect()


if __name__ == "__main__":
    main()
