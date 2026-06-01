"""Per-experiment AI provider: AI session lives within a mode.

A separate "monitoring" AI scan runs between experiments to feed the
Values sidebar. When an experiment mode arms, the monitoring scan is
torn down so the mode can claim AI with its own parameters; when the
mode finishes, the monitoring scan is restarted.

This is the alternative to :class:`PersistentAIProvider`. It is the
shape closest to the legacy IR-branch ``DAQController`` (and to the
Bondar C++ code's NShot-per-experiment pattern). The pause/resume
choreography is what we wanted to avoid in the persistent design, but
this implementation is kept as an empirical fallback (see
``docs/live-streaming.md`` section 13.2 and 13.4).

For the first iteration (where experiment modes have not yet been
refactored to call back through the AIProvider), the practical
difference from :class:`PersistentAIProvider` is only visible during
``arm_for_experiment`` / ``end_of_experiment``: those hooks stop and
restart the AI scan, where the persistent provider does nothing.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

import numpy as np

from pioner.back.acquisition.base import AIProvider, AcquisitionMode
from pioner.back.experiment_manager import ExperimentManager

logger = logging.getLogger(__name__)


class PerExperimentAIProvider(AIProvider):
    """AI scan armed for monitoring; paused around experiment runs.

    Parameters
    ----------
    em
        The owning :class:`ExperimentManager`.
    ring_max_seconds
        Depth of in-RAM history for the monitoring scan. Default 2 s.
    """

    def __init__(
        self,
        em: ExperimentManager,
        ring_max_seconds: float = 2.0,
    ) -> None:
        self._em = em
        self._ring_max_seconds = float(ring_max_seconds)
        self._ai_channels: Optional[list[int]] = None
        self._connected = False
        self._monitoring = False

    @property
    def mode(self) -> AcquisitionMode:
        return AcquisitionMode.PER_EXPERIMENT

    def on_connect(self, ai_channels: Sequence[int]) -> None:
        """Open the monitoring scan after DAQ open."""
        if self._connected:
            logger.warning("PerExperimentAIProvider.on_connect called while connected; ignoring")
            return
        self._ai_channels = list(ai_channels)
        self._connected = True
        self._start_monitoring()
        logger.info(
            "Per-experiment monitoring AI started: channels=%s, ring_max_seconds=%.2f",
            self._ai_channels, self._ring_max_seconds,
        )

    def on_disconnect(self) -> None:
        """Stop monitoring and release AI."""
        if not self._connected:
            return
        try:
            self._stop_monitoring()
        finally:
            self._connected = False
            self._ai_channels = None
            logger.info("Per-experiment AI provider disconnected")

    def arm_for_experiment(self) -> None:
        """Pause monitoring so the mode can claim AI for its own scan."""
        if self._monitoring:
            self._stop_monitoring()
            logger.debug("Per-experiment provider: monitoring paused for experiment")

    def end_of_experiment(self) -> None:
        """Restart monitoring after the experiment.

        Called from the UI's ``finally`` block of the mode run so that
        even an exception in the experiment leaves the system in a
        well-defined monitoring state.
        """
        if self._connected and not self._monitoring:
            self._start_monitoring()
            logger.debug("Per-experiment provider: monitoring resumed after experiment")

    def peek_last(self, samples: int) -> np.ndarray:
        if not self._monitoring:
            return np.empty((0, 0), dtype=float)
        return self._em.peek_last_samples(samples)

    def read_new(self, consumer_id: str) -> np.ndarray:
        if not self._monitoring:
            return np.empty((0, 0), dtype=float)
        return self._em.read_new_samples(consumer_id)

    def is_active(self) -> bool:
        return self._monitoring

    # ------------------------------------------------------------------
    # Internal lifecycle helpers
    # ------------------------------------------------------------------
    def _start_monitoring(self) -> None:
        if self._ai_channels is None:
            raise RuntimeError("PerExperimentAIProvider has no AI channels configured")
        self._em.start_ring_buffer(self._ai_channels, max_seconds=self._ring_max_seconds)
        self._monitoring = True

    def _stop_monitoring(self) -> None:
        if not self._monitoring:
            return
        try:
            self._em.stop_ring_buffer()
        finally:
            self._monitoring = False


__all__ = ["PerExperimentAIProvider"]
