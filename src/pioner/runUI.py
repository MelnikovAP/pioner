"""Entry point for the PIONER GUI (single window for all modes).

Backend selection:

* ``--mock``     force the in-process LocalDeviceController (mock DAQ when
                 no MCC board is attached). Live streaming + experiments
                 run without any Tango server.
* ``--hardware`` force the legacy Tango network backend.
* (default)      autodetect -- if PyTango is not importable, pre-select the
                 local/mock backend.

The flag only pre-selects the "run without hardware" checkbox; the
operator still presses ON to connect (so they can review settings first).
"""

import argparse
import sys

from silx.gui import qt

from pioner.front.mainWindow import mainWindow


def pioner_run_ui(argv=None):
    parser = argparse.ArgumentParser(prog="pioner.runUI", description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--mock", action="store_true",
                       help="force local mock backend (no Tango)")
    group.add_argument("--hardware", action="store_true",
                       help="force legacy Tango hardware backend")
    args = parser.parse_args(argv)

    app = qt.QApplication([])
    sys.excepthook = qt.exceptionHandler  # type: ignore[attr-defined]
    app.setStyle('Fusion')
    window = mainWindow()

    if args.mock:
        window.sysNoHardware.setChecked(True)
    elif args.hardware:
        window.sysNoHardware.setChecked(False)
    else:
        # Autodetect: without PyTango the Tango path cannot work, so
        # default to the local/mock backend.
        try:
            import tango  # noqa: F401
        except Exception:
            window.sysNoHardware.setChecked(True)

    window.showMaximized()
    app.exec()


if __name__ == "__main__":
    pioner_run_ui()
