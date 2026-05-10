"""Sanity checks for the mock uldaq backend.

These tests focus on the actual contract the rest of the code relies on:
buffer is shared, scan progresses, stop releases the worker. Anything beyond
that (AO/AI integration, calibration, etc.) is covered in higher-level
e2e tests.
"""

# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# Real uldaq stubs are stricter than the mock surface (enum flags, ctypes
# Array[float] vs list[float], etc.). Tests are runtime-verified.
from __future__ import annotations

import time

import pytest

from pioner.back.mock_uldaq import DAQ_AVAILABLE, uldaq

# These tests only target the mock backend; if a real driver is installed,
# the implementation is provided by Measurement Computing and we trust their
# own test suite.
pytestmark = pytest.mark.skipif(
    DAQ_AVAILABLE, reason="real uldaq backend present, mock-specific tests skipped"
)


def _make_device():
    return uldaq.DaqDevice(uldaq.DaqDeviceDescriptor())


def test_lifecycle():
    dev = _make_device()
    assert not dev.is_connected()
    dev.connect()
    assert dev.is_connected()
    dev.disconnect()
    assert not dev.is_connected()
    dev.release()


def test_create_float_buffer_shape():
    buf = uldaq.create_float_buffer(4, 100)
    assert isinstance(buf, list)
    assert len(buf) == 400


def test_ai_scan_progresses_and_stops():
    dev = _make_device()
    dev.connect()
    ai = dev.get_ai_device()
    buf = uldaq.create_float_buffer(2, 1000)
    ai.a_in_scan(0, 1, uldaq.AiInputMode.SINGLE_ENDED, uldaq.Range(5),
                 1000, 1000.0, uldaq.ScanOption.CONTINUOUS, 0, buf)
    time.sleep(0.5)
    status, transfer = ai.get_scan_status()
    assert status == uldaq.ScanStatus.RUNNING
    assert transfer.current_scan_count > 0
    ai.scan_stop()
    time.sleep(0.05)
    status, _ = ai.get_scan_status()
    assert status == uldaq.ScanStatus.IDLE


def test_ai_buffer_is_shared_not_copied():
    dev = _make_device()
    dev.connect()
    ai = dev.get_ai_device()
    buf = uldaq.create_float_buffer(1, 200)
    ao = dev.get_ao_device()
    # Drive a known voltage on AO ch0 so the AI mock has something to mirror.
    ao_buf = [3.0] * 100
    ao.a_out_scan(0, 0, uldaq.Range(5), 100, 100.0, uldaq.ScanOption.CONTINUOUS, 0, ao_buf)
    ai.a_in_scan(0, 0, uldaq.AiInputMode.SINGLE_ENDED, uldaq.Range(5),
                 200, 200.0, uldaq.ScanOption.CONTINUOUS, 0, buf)
    time.sleep(0.5)
    ai.scan_stop()
    ao.scan_stop()
    # ``ai.get_buffer`` should hand back the same list object we passed in.
    assert ai.get_buffer() is buf
    # The list must have been mutated in place; not all entries should be 0.
    assert any(abs(v) > 1e-9 for v in buf)


def test_ao_iso_voltage():
    dev = _make_device()
    dev.connect()
    ao = dev.get_ao_device()
    result = ao.a_out(0, uldaq.Range(5), 0, 2.5)
    assert result == 2.5
