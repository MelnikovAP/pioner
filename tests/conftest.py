"""Common pytest fixtures for the pioner test suite."""

from __future__ import annotations

import os
import sys

import pytest

# Make ``src/`` importable without a full ``pip install -e``.
_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "src")))

from pioner.shared.calibration import Calibration  # noqa: E402
from pioner.shared.constants import DEFAULT_SETTINGS_FILE_REL_PATH  # noqa: E402
from pioner.shared.settings import BackSettings  # noqa: E402
from pioner.back.daq_device import DaqDeviceHandler  # noqa: E402


@pytest.fixture
def settings() -> BackSettings:
    return BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH)


@pytest.fixture
def calibration() -> Calibration:
    return Calibration()


@pytest.fixture
def connected_daq(settings: BackSettings):
    handler = DaqDeviceHandler(settings.daq_params)
    handler.try_connect()
    try:
        yield handler
    finally:
        handler.quit()
