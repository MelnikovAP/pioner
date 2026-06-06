"""Tests for DiskRecorder -- record-from-arm raw capture (P1-17 step 2).

A fake ring stands in for ``ExperimentManager``: it mimics the single,
destructive per-consumer cursor (``read_new_samples`` hands back everything
queued since the last call and clears the queue). Correctness here does not
depend on the background thread's timing -- ``mark_start`` and ``stop`` each
drain explicitly, so every fed chunk is captured and the mark always lands at
the baseline|run boundary.
"""

from __future__ import annotations

import threading

import numpy as np
import pytest

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


def _recorder(ring) -> DiskRecorder:
    # Tiny poll so the background thread is lively; correctness is independent
    # of it anyway (mark_start / stop drain explicitly).
    return DiskRecorder(ring, consumer_id="test", poll_interval=0.01)


def test_records_baseline_and_run_with_mark():
    ring = FakeRing(channels=3)
    rec = _recorder(ring)
    rec.start()
    try:
        ring.feed(40, 1.0)      # baseline (arm -> start)
        rec.mark_start()        # boundary
        ring.feed(100, 2.0)     # run
    finally:
        raw = rec.stop()
    assert raw.shape == (140, 3)
    assert rec.mark_index == 40
    # Baseline rows are the 1.0 block, run rows the 2.0 block, in order.
    assert np.all(raw[:40] == 1.0)
    assert np.all(raw[40:] == 2.0)


def test_start_primes_cursor_and_drops_backlog():
    ring = FakeRing(channels=2)
    rec = _recorder(ring)
    ring.feed(99, 7.0)          # pre-arm backlog, must be discarded
    rec.start()                 # primes: reset + one discarded read
    try:
        ring.feed(10, 1.0)
    finally:
        raw = rec.stop()
    assert ring.reset_calls == 1
    assert raw.shape == (10, 2)
    assert np.all(raw == 1.0)   # backlog never captured


def test_mark_index_none_until_marked():
    ring = FakeRing()
    rec = _recorder(ring)
    rec.start()
    try:
        assert rec.mark_index is None
        ring.feed(5, 1.0)
    finally:
        rec.stop()
    assert rec.mark_index is None  # never marked


def test_stop_without_data_returns_empty():
    ring = FakeRing()
    rec = _recorder(ring)
    rec.start()
    raw = rec.stop()
    assert raw.shape == (0, 0)


def test_double_start_is_ignored():
    ring = FakeRing()
    rec = _recorder(ring)
    rec.start()
    try:
        assert rec.is_recording
        rec.start()  # second call is a no-op (logs a warning)
        assert rec.is_recording
    finally:
        rec.stop()
    assert not rec.is_recording


def test_chunk_order_preserved_across_many_feeds():
    ring = FakeRing(channels=1)
    rec = _recorder(ring)
    rec.start()
    # Feed 20 distinct blocks; the queue preserves order, and whatever the
    # background thread does not drain, stop()'s final drain picks up -- so the
    # assembled frame is the feeds strictly in order regardless of timing.
    for i in range(20):
        ring.feed(3, float(i))
    raw = rec.stop()
    assert raw.shape == (60, 1)
    expected = np.repeat(np.arange(20, dtype=float), 3).reshape(-1, 1)
    assert np.array_equal(raw, expected)
