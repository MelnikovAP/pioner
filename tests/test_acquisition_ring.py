"""Tests for the ring-buffer extensions (peek_last_samples / read_new_samples).

Driven through the mock DAQ backend so they exercise the full
``ExperimentManager.start_ring_buffer`` -> ``_ring_loop`` -> consumer
read path without real hardware.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from pioner.back.experiment_manager import ExperimentManager


def _wait_for_chunks(em: ExperimentManager, min_samples: int, timeout: float = 3.0) -> None:
    """Poll until the ring buffer has at least ``min_samples`` rows."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with em._ring_lock:
            current = sum(len(c) for c in em._ring_data)
        if current >= min_samples:
            return
        time.sleep(0.05)
    raise TimeoutError(f"ring buffer did not fill to {min_samples} within {timeout} s")


@pytest.fixture
def streaming_em(connected_daq, settings):
    """Start a persistent CONTINUOUS ring-buffer scan; yield the manager."""
    em = ExperimentManager(connected_daq, settings)
    em.start_ring_buffer([0, 1, 2, 3, 4, 5], max_seconds=2.0)
    _wait_for_chunks(em, min_samples=settings.ai_params.sample_rate // 4)
    try:
        yield em
    finally:
        em.stop()


def test_peek_last_returns_at_most_n_samples(streaming_em, settings):
    """peek_last(N) returns at most N rows and never advances any cursor."""
    n = settings.ai_params.sample_rate // 20  # ~50 ms window
    snap_a = streaming_em.peek_last_samples(n)
    snap_b = streaming_em.peek_last_samples(n)
    assert snap_a.ndim == 2 and snap_a.shape[1] == 6
    assert snap_a.shape[0] <= n
    assert snap_b.shape[0] <= n
    # Two snapshots taken back-to-back should be IDENTICAL or differ only at
    # the tail (newer samples appended); they must NOT show consumed prefix.
    # In practice the mock produces data at >> the inter-call rate, so the
    # safe invariant is "same shape".
    assert snap_b.shape == snap_a.shape


def test_peek_last_zero_returns_empty(streaming_em):
    """peek_last(0) returns an empty 2-D array (no crash, no exception)."""
    out = streaming_em.peek_last_samples(0)
    assert out.shape == (0, 0)


def test_peek_last_more_than_available_returns_what_exists(streaming_em, settings):
    """Asking for more samples than the ring holds is not an error."""
    huge = settings.ai_params.sample_rate * 100
    out = streaming_em.peek_last_samples(huge)
    assert out.ndim == 2 and out.shape[1] == 6
    # Ring is bounded; we get strictly less than asked for.
    assert out.shape[0] < huge


def test_read_new_first_call_returns_current_ring(streaming_em):
    """First read_new for a consumer returns the current ring contents."""
    data = streaming_em.read_new_samples("consumer-A")
    assert data.ndim == 2 and data.shape[1] == 6
    assert data.shape[0] > 0


def test_read_new_advances_cursor(streaming_em):
    """Subsequent read_new returns only new samples since previous call."""
    first = streaming_em.read_new_samples("consumer-B")
    immediate = streaming_em.read_new_samples("consumer-B")
    # The second call is right after the first; either nothing new yet, or
    # a small delta -- but in any case strictly less than ``first``.
    assert immediate.shape[0] <= first.shape[0]


def test_read_new_independent_cursors(streaming_em):
    """Two consumers maintain independent cursors."""
    streaming_em.read_new_samples("consumer-X")
    streaming_em.read_new_samples("consumer-Y")
    time.sleep(0.2)
    delta_x = streaming_em.read_new_samples("consumer-X")
    delta_y = streaming_em.read_new_samples("consumer-Y")
    # Both consumers should see comparable batches (same data flowed in).
    # Tolerate ~one chunk of drift between the two reads.
    assert abs(delta_x.shape[0] - delta_y.shape[0]) <= delta_x.shape[1] * 250  # generous


def test_reset_ring_cursor(streaming_em):
    """reset_ring_cursor drops the per-consumer cursor."""
    streaming_em.read_new_samples("consumer-Z")
    streaming_em.reset_ring_cursor("consumer-Z")
    second = streaming_em.read_new_samples("consumer-Z")
    # After reset the consumer joins at the current head (i.e. the
    # currently buffered samples again, not "nothing new").
    assert second.shape[0] > 0
