"""Tests for finalize_raw_to_h5 -- chunked raw(U) -> calibrated(T) file (P1-17 step 4c-1).

Finalise streams the raw recorder file block-by-block into a separate calibrated
file (the result lives on disk; finalise returns a summary dict, not a frame).
The key correctness check is that the chunked output equals a whole-frame
``apply_calibration`` reference.
"""

from __future__ import annotations

from typing import cast

import h5py
import numpy as np
import pandas as pd
import pytest

from pioner.back.acquisition.disk_recorder import DiskRecorder
from pioner.back.modes import (
    DEFAULT_AI_CHANNELS,
    apply_calibration,
    finalize_raw_to_h5,
    read_calibrated_h5,
)
from pioner.shared.calibration import Calibration
from pioner.shared.constants import DEFAULT_SETTINGS_FILE_REL_PATH
from pioner.shared.modulation import ModulationParams
from pioner.shared.settings import BackSettings


class FakeRing:
    """Destructive single-cursor ring stub (matches ExperimentManager's API)."""

    def __init__(self, channels: int):
        self._channels = channels
        self._queue: list[np.ndarray] = []

    def feed(self, arr: np.ndarray) -> None:
        self._queue.append(np.asarray(arr, dtype=float))

    def reset_ring_cursor(self, consumer_id: str) -> None:
        pass

    def read_new_samples(self, consumer_id: str) -> np.ndarray:
        if not self._queue:
            return np.empty((0, 0), dtype=float)
        out = np.concatenate(self._queue, axis=0)
        self._queue = []
        return out


def _write_raw(path: str, raw: np.ndarray) -> None:
    ring = FakeRing(raw.shape[1])
    rec = DiskRecorder(ring, path, consumer_id="t", poll_interval=0.01)
    rec.start()
    ring.feed(raw)
    rec.stop()


def _read_col(path: str, col: str) -> np.ndarray:
    with h5py.File(path, "r") as f:
        data = cast(h5py.Group, f["data"])
        return cast(h5py.Dataset, data[col])[:]


def _read_cols(path: str) -> list[str]:
    with h5py.File(path, "r") as f:
        return list(cast(h5py.Group, f["data"]).keys())


def test_finalize_writes_separate_calibrated_file(tmp_path):
    raw_path = str(tmp_path / "scan_raw.h5")   # U (volts)
    out_path = str(tmp_path / "scan.h5")       # T (engineering units)
    raw = np.random.default_rng(0).uniform(0.1, 1.0, size=(2000, len(DEFAULT_AI_CHANNELS)))
    _write_raw(raw_path, raw)

    settings = BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH)
    summary = finalize_raw_to_h5(
        raw_path, out_path,
        sample_rate=2000.0,
        calibration=Calibration(),
        settings=settings,
        voltage_profiles={"ch1": np.linspace(0.0, 1.0, 2000)},
        programs={"ch1": {"time": [0, 1000], "volt": [0, 1]}},
        ai_channels=DEFAULT_AI_CHANNELS,
    )
    assert summary is not None and summary["rows"] == 2000  # dict, not a DataFrame
    for col in ("time", "Taux", "Thtr", "temp", "Uref"):
        assert col in _read_cols(out_path)
    assert len(_read_col(out_path, "temp")) == 2000

    # Raw (U) file untouched.
    import os
    assert os.path.abspath(raw_path) != os.path.abspath(out_path)
    with h5py.File(raw_path, "r") as f:
        assert np.array_equal(cast(h5py.Dataset, f["raw_ai"])[:], raw)


def test_finalize_chunked_matches_whole_frame(tmp_path):
    """Block-by-block finalise must equal a single whole-frame apply_calibration."""
    raw_path = str(tmp_path / "raw.h5")
    out_path = str(tmp_path / "cal.h5")
    n = 1500
    raw = np.random.default_rng(1).uniform(0.1, 1.0, size=(n, len(DEFAULT_AI_CHANNELS)))
    _write_raw(raw_path, raw)
    profile = np.linspace(0.0, 1.0, n)

    ref = apply_calibration(
        pd.DataFrame(raw, columns=list(DEFAULT_AI_CHANNELS)),
        sample_rate=2000.0,
        calibration=Calibration(),
        voltage_profiles={"ch1": profile},
        ai_channels=DEFAULT_AI_CHANNELS,
    )

    finalize_raw_to_h5(
        raw_path, out_path,
        sample_rate=2000.0,
        calibration=Calibration(),
        settings=BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH),
        voltage_profiles={"ch1": profile},
        programs={"ch1": {"time": [0, 750], "volt": [0, 1]}},
        ai_channels=DEFAULT_AI_CHANNELS,
        block_rows=137,   # force many partial blocks
    )
    for col in ("time", "Taux", "Thtr", "temp", "temp-hr", "Uref"):
        assert np.allclose(_read_col(out_path, col), ref[col].to_numpy(), equal_nan=True), col


def test_finalize_lockin_columns_with_modulation(tmp_path):
    raw_path = str(tmp_path / "raw.h5")
    out_path = str(tmp_path / "cal.h5")
    n = 2000
    raw = np.random.default_rng(2).uniform(0.1, 1.0, size=(n, len(DEFAULT_AI_CHANNELS)))
    _write_raw(raw_path, raw)
    summary = finalize_raw_to_h5(
        raw_path, out_path,
        sample_rate=2000.0,
        calibration=Calibration(),
        settings=BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH),
        voltage_profiles={"ch1": np.linspace(0.0, 1.0, n)},
        programs={"ch1": {"time": [0, 1000], "volt": [0, 1]}},
        ai_channels=DEFAULT_AI_CHANNELS,
        modulation=ModulationParams(frequency=100.0, amplitude=0.1, offset=0.0),
        block_rows=512,
    )
    assert summary is not None
    cols = _read_cols(out_path)
    for col in ("temp-hr_amp", "temp-hr_phase", "temp-hr_valid"):
        assert col in cols
        assert len(_read_col(out_path, col)) == n


def test_finalize_program_offset_marks_baseline_uref_nan(tmp_path):
    """Rows before program_offset are baseline -> Uref is NaN there."""
    raw_path = str(tmp_path / "raw.h5")
    out_path = str(tmp_path / "cal.h5")
    n, offset = 1000, 300
    raw = np.random.default_rng(3).uniform(0.1, 1.0, size=(n, len(DEFAULT_AI_CHANNELS)))
    _write_raw(raw_path, raw)
    ramp = np.linspace(0.0, 1.0, n - offset)
    finalize_raw_to_h5(
        raw_path, out_path,
        sample_rate=2000.0,
        calibration=Calibration(),
        settings=BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH),
        voltage_profiles={"ch1": ramp},
        programs={"ch1": {"time": [0, 350], "volt": [0, 1]}},
        ai_channels=DEFAULT_AI_CHANNELS,
        block_rows=128,
        program_offset=offset,
    )
    uref = _read_col(out_path, "Uref")
    assert np.all(np.isnan(uref[:offset]))            # baseline
    assert np.allclose(uref[offset:], ramp)           # ramp aligned at the mark


def test_read_calibrated_decimation(tmp_path):
    raw_path = str(tmp_path / "raw.h5")
    out_path = str(tmp_path / "cal.h5")
    n = 2000
    raw = np.random.default_rng(4).uniform(0.1, 1.0, size=(n, len(DEFAULT_AI_CHANNELS)))
    _write_raw(raw_path, raw)
    finalize_raw_to_h5(
        raw_path, out_path,
        sample_rate=2000.0,
        calibration=Calibration(),
        settings=BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH),
        voltage_profiles={"ch1": np.linspace(0.0, 1.0, n)},
        programs={"ch1": {"time": [0, 1000], "volt": [0, 1]}},
        ai_channels=DEFAULT_AI_CHANNELS,
    )

    # step: every 10th sample.
    every10 = read_calibrated_h5(out_path, step=10)
    assert len(every10["temp"]) == int(np.ceil(n / 10))

    # max_points: auto-stride to <= the target.
    capped = read_calibrated_h5(out_path, max_points=100)
    assert 0 < len(capped["temp"]) <= 100

    # column subset.
    subset = read_calibrated_h5(out_path, columns=["time", "temp"], step=5)
    assert set(subset) == {"time", "temp"}

    # full read (step=1) returns every sample.
    full = read_calibrated_h5(out_path, columns=["temp"], step=1)
    assert len(full["temp"]) == n


def test_finalize_rejects_same_path(tmp_path):
    raw_path = str(tmp_path / "same.h5")
    _write_raw(raw_path, np.zeros((10, len(DEFAULT_AI_CHANNELS))))
    with pytest.raises(ValueError):
        finalize_raw_to_h5(
            raw_path, raw_path,
            sample_rate=2000.0,
            calibration=Calibration(),
            settings=BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH),
            voltage_profiles={"ch1": np.zeros(10)},
            programs={"ch1": {"time": [0, 5], "volt": [0, 0]}},
            ai_channels=DEFAULT_AI_CHANNELS,
        )


def test_finalize_empty_raw_returns_none(tmp_path):
    raw_path = str(tmp_path / "empty_raw.h5")
    out_path = str(tmp_path / "empty.h5")
    ring = FakeRing(len(DEFAULT_AI_CHANNELS))
    rec = DiskRecorder(ring, raw_path, consumer_id="t", poll_interval=0.01)
    rec.start()
    rec.stop()
    summary = finalize_raw_to_h5(
        raw_path, out_path,
        sample_rate=2000.0,
        calibration=Calibration(),
        settings=BackSettings(DEFAULT_SETTINGS_FILE_REL_PATH),
        voltage_profiles={"ch1": np.zeros(1)},
        programs={"ch1": {"time": [0, 1], "volt": [0, 0]}},
        ai_channels=DEFAULT_AI_CHANNELS,
    )
    assert summary is None
