"""Tests for the AIProvider abstraction.

Both implementations are exercised through the mock DAQ. The tests
verify the interface contract (lifecycle hooks, peek/read_new) and the
behavioural difference between persistent and per-experiment modes
during the arm/end-of-experiment hooks.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from pioner.back.acquisition import (
    AIProvider,
    AcquisitionMode,
    PersistentAIProvider,
    PerExperimentAIProvider,
    create_ai_provider,
)
from pioner.back.experiment_manager import ExperimentManager


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
class TestAcquisitionModeParser:
    """Lenient string parser at the config edge."""

    def test_default_for_missing(self):
        assert AcquisitionMode.from_string(None) is AcquisitionMode.PERSISTENT
        assert AcquisitionMode.from_string("") is AcquisitionMode.PERSISTENT

    def test_default_for_unknown(self):
        assert AcquisitionMode.from_string("xyz") is AcquisitionMode.PERSISTENT

    def test_known_values(self):
        assert AcquisitionMode.from_string("persistent") is AcquisitionMode.PERSISTENT
        assert AcquisitionMode.from_string("per_experiment") is AcquisitionMode.PER_EXPERIMENT

    def test_whitespace_and_case_tolerant(self):
        assert AcquisitionMode.from_string(" Persistent ") is AcquisitionMode.PERSISTENT
        assert AcquisitionMode.from_string("PER_EXPERIMENT") is AcquisitionMode.PER_EXPERIMENT


class TestFactory:
    def test_creates_persistent_by_default(self, connected_daq, settings):
        em = ExperimentManager(connected_daq, settings)
        provider = create_ai_provider(None, em)
        assert isinstance(provider, PersistentAIProvider)
        assert provider.mode is AcquisitionMode.PERSISTENT

    def test_creates_per_experiment_when_requested(self, connected_daq, settings):
        em = ExperimentManager(connected_daq, settings)
        provider = create_ai_provider("per_experiment", em)
        assert isinstance(provider, PerExperimentAIProvider)
        assert provider.mode is AcquisitionMode.PER_EXPERIMENT

    def test_falls_back_on_unknown_string(self, connected_daq, settings):
        em = ExperimentManager(connected_daq, settings)
        provider = create_ai_provider("garbage", em)
        assert isinstance(provider, PersistentAIProvider)


# ---------------------------------------------------------------------------
# Shared behaviour
# ---------------------------------------------------------------------------
def _wait_for_active(provider: AIProvider, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = provider.peek_last(1000)
        if data.shape[0] > 0:
            return
        time.sleep(0.05)
    raise TimeoutError("provider did not produce any samples within the timeout")


@pytest.fixture(params=["persistent", "per_experiment"])
def provider(request, connected_daq, settings):
    """Parametrised fixture: each test runs against both providers."""
    em = ExperimentManager(connected_daq, settings)
    p = create_ai_provider(request.param, em, ring_max_seconds=1.0)
    p.on_connect(ai_channels=[0, 1, 2, 3, 4, 5])
    _wait_for_active(p)
    try:
        yield p
    finally:
        p.on_disconnect()
        em.stop()


class TestSharedBehaviour:
    """Tests that must pass for both providers."""

    def test_peek_returns_2d_with_six_channels(self, provider):
        data = provider.peek_last(200)
        assert data.ndim == 2
        assert data.shape[1] == 6
        assert data.shape[0] > 0
        assert data.shape[0] <= 200

    def test_read_new_returns_data_then_diminishes(self, provider):
        first = provider.read_new("consumer-1")
        assert first.shape[0] > 0
        second = provider.read_new("consumer-1")
        # Right after, only the small delta has arrived.
        assert second.shape[0] <= first.shape[0]

    def test_independent_consumers(self, provider):
        a = provider.read_new("a")
        b = provider.read_new("b")
        # Independent first-reads return comparable batches (no
        # consumption interference).
        assert a.shape[0] > 0
        assert b.shape[0] > 0

    def test_on_disconnect_is_idempotent(self, provider):
        provider.on_disconnect()
        provider.on_disconnect()  # no exception
        assert not provider.is_active()
        # After disconnect, peek and read_new return empty rather than raise.
        assert provider.peek_last(100).shape == (0, 0)
        assert provider.read_new("any-id").shape == (0, 0)


# ---------------------------------------------------------------------------
# Provider-specific behaviour
# ---------------------------------------------------------------------------
class TestPersistentArmIsNoOp:
    """In persistent mode, arm/end hooks must not stop the AI scan."""

    def test_arm_keeps_ai_running(self, connected_daq, settings):
        em = ExperimentManager(connected_daq, settings)
        provider = PersistentAIProvider(em, ring_max_seconds=1.0)
        provider.on_connect(ai_channels=[0, 1, 2, 3, 4, 5])
        _wait_for_active(provider)
        try:
            assert provider.is_active()
            provider.arm_for_experiment()
            assert provider.is_active()  # still running
            provider.end_of_experiment()
            assert provider.is_active()  # still running
        finally:
            provider.on_disconnect()
            em.stop()


class TestPerExperimentArmPausesAndResumes:
    """In per-experiment mode, arm stops monitoring; end restarts it."""

    def test_arm_stops_monitoring_end_restarts(self, connected_daq, settings):
        em = ExperimentManager(connected_daq, settings)
        provider = PerExperimentAIProvider(em, ring_max_seconds=1.0)
        provider.on_connect(ai_channels=[0, 1, 2, 3, 4, 5])
        _wait_for_active(provider)
        try:
            assert provider.is_active()
            provider.arm_for_experiment()
            assert not provider.is_active()  # paused
            # Peek now returns empty -- AI is not running.
            assert provider.peek_last(100).shape == (0, 0)
            provider.end_of_experiment()
            assert provider.is_active()  # resumed
            _wait_for_active(provider)
            assert provider.peek_last(100).shape[0] > 0
        finally:
            provider.on_disconnect()
            em.stop()
