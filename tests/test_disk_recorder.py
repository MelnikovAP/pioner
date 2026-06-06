"""Tests for DiskRecorder -- streaming record-from-arm to HDF5 (P1-17 step 2).

A fake ring stands in for ``ExperimentManager``: it mimics the single,
destructive per-consumer cursor (``read_new_samples`` hands back everything
queued since the last call and clears the queue). Each test reads the produced
HDF5 file back and checks the capture is lossless and order-preserving, that the
mark lands at the baseline|run boundary, and that nothing is held in memory
(samples go straight to ``raw_ai`` on disk). Correctness is independent of the
background thread's timing -- ``mark_start`` and ``stop`` each drain explicitly.
"""

from __future__ import annotations

import threading

import h5py
import numpy as np

from pioner.back.acquisition.disk_recorder import DiskRecorder


class FakeRing:
    """Mimics the ring's destructive per-consumer cursor + reset."""

    def __init__(self, channels: int = 3):
        self._channels = channels
        self._queue: list[np.ndarray] = []
        self._lock = threading.Lock()
        self.reset_calls = 0

    def feed(self, n_rows: int, value: float) -> None:
        with self._lock:
            self._queue.append(np.full((n_rows, self._channels), value, dtype=float))

    def reset_ring_cursor(self, consumer_id: str) -> None:
        self.reset_calls += 1

    def read_new_samples(self, consumer_id: str) -> np.ndarray:
        with self._lock:
            if not self._queue:
                return np.empty((0, 0), dtype=float)
            out = np.concatenate(self._queue, axis=0)
            self._queue = []
            return out


def _recorder(ring, tmp_path) -> DiskRecorder:
    return DiskRecorder(
        ring, str(tmp_path / "raw.h5"), consumer_id="test", poll_interval=0.01
    )


def _read(path):
    with h5py.File(path, "r") as f:
        raw = f["raw_ai"][:] if "raw_ai" in f else np.empty((0, 0))
        rows = int(f.attrs["rows"])
        mark = int(f.attrs["mark_index"])
    return raw, rows, mark


def test_records_baseline_and_run_with_mark(tmp_path):
    ring = FakeRing(channels=3)
    rec = _recorder(ring, tmp_path)
    rec.start()
    ring.feed(40, 1.0)      # baseline (arm -> start)
    rec.mark_start()        # boundary
    ring.feed(100, 2.0)     # run
    path = rec.stop()

    raw, rows, mark = _read(path)
    assert raw.shape == (140, 3)
    assert rows == 140
    assert mark == 40
    assert rec.mark_index == 40
    assert np.all(raw[:40] == 1.0)
    assert np.all(raw[40:] == 2.0)


def test_start_primes_cursor_and_drops_backlog(tmp_path):
    ring = FakeRing(channels=2)
    rec = _recorder(ring, tmp_path)
    ring.feed(99, 7.0)      # pre-arm backlog, must be discarded
    rec.start()             # primes: reset + one discarded read
    ring.feed(10, 1.0)
    path = rec.stop()

    raw, rows, _ = _read(path)
    assert ring.reset_calls == 1
    assert raw.shape == (10, 2)
    assert rows == 10
    assert np.all(raw == 1.0)   # backlog never captured


def test_mark_index_minus_one_when_never_marked(tmp_path):
    ring = FakeRing()
    rec = _recorder(ring, tmp_path)
    rec.start()
    assert rec.mark_index is None
    ring.feed(5, 1.0)
    path = rec.stop()
    _, rows, mark = _read(path)
    assert rows == 5
    assert mark == -1            # sentinel for "never marked"


def test_stop_without_data_writes_empty_file(tmp_path):
    ring = FakeRing()
    rec = _recorder(ring, tmp_path)
    rec.start()
    path = rec.stop()
    with h5py.File(path, "r") as f:
        assert "raw_ai" not in f       # no chunk -> dataset never created
        assert int(f.attrs["rows"]) == 0
        assert int(f.attrs["mark_index"]) == -1


def test_double_start_is_ignored(tmp_path):
    ring = FakeRing()
    rec = _recorder(ring, tmp_path)
    rec.start()
    assert rec.is_recording
    rec.start()  # no-op (logs a warning)
    assert rec.is_recording
    rec.stop()
    assert not rec.is_recording


def test_chunk_order_preserved_across_many_feeds(tmp_path):
    ring = FakeRing(channels=1)
    rec = _recorder(ring, tmp_path)
    rec.start()
    # Feed 20 distinct blocks; the queue preserves order, and whatever the
    # background thread does not drain, stop()'s final drain picks up -- so the
    # streamed dataset is the feeds strictly in order regardless of timing.
    for i in range(20):
        ring.feed(3, float(i))
    path = rec.stop()

    raw, rows, _ = _read(path)
    assert raw.shape == (60, 1)
    assert rows == 60
    expected = np.repeat(np.arange(20, dtype=float), 3).reshape(-1, 1)
    assert np.array_equal(raw, expected)
