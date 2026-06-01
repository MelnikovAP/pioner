"""Persistent AI provider: one scan from Connect to Disconnect.

The scan is armed once when the DAQ is opened and runs in
``ScanOption.CONTINUOUS`` mode until the DAQ is closed. Experiment
modes do not touch AI -- they only command AO. All readers (Values
sidebar, slow-heat live plot, disk recorder) read the same ring buffer
through their own private cursors.

This is the recommended default. Rationale and trade-offs are in
``docs/live-streaming.md`` sections 3 and 13.
"""

from __future__ import annotations

import logging
from typing import Optional, Sequence

import numpy as np

from pioner.back.acquisition.base import AIProvider, AcquisitionMode
from pioner.back.experiment_manager import ExperimentManager

logger = logging.getLogger(__name__)


class PersistentAIProvider(AIProvider):
    """One persistent AI scan, multi-consumer access via the ring buffer.

    Parameters
    ----------
    em
        The owning :class:`ExperimentManager`. Its ``start_ring_buffer`` /
        ``stop_ring_buffer`` / ``peek_last_samples`` / ``read_new_samples``
        methods are what we drive.
    ring_max_seconds
        Depth of in-RAM history kept available for late-arriving consumers.
        Default 2 s -- enough for the UI sliding-window demod (typically
        0.1-0.5 s) plus a comfortable safety margin against Python GIL
        stalls. Bigger only matters if a slow disk recorder needs more
        backlog tolerance.
    """

    def __init__(
        self,
        em: ExperimentManager,
        ring_max_seconds: float = 2.0,
    ) -> None:
        self._em = em
        self._ring_max_seconds = float(ring_max_seconds)
        self._ai_channels: Optional[list[int]] = None
        self._active = False

    @property
    def mode(self) -> AcquisitionMode:
        return AcquisitionMode.PERSISTENT

    def on_connect(self, ai_channels: Sequence[int]) -> None:
        """Arm the persistent AI scan immediately after DAQ open."""
        if self._active:
            logger.warning("PersistentAIProvider.on_connect called while already active; ignoring")
            return
        self._ai_channels = list(ai_channels)
        self._em.start_ring_buffer(
            self._ai_channels,
            max_seconds=self._ring_max_seconds,
        )
        self._active = True
        logger.info(
            "Persistent AI started: channels=%s, ring_max_seconds=%.2f",
            self._ai_channels, self._ring_max_seconds,
        )

    def on_disconnect(self) -> None:
        """Stop the persistent AI scan."""
        if not self._active:
            return
        try:
            self._em.stop_ring_buffer()
        finally:
            self._active = False
            logger.info("Persistent AI stopped")

    def arm_for_experiment(self) -> None:
        """No-op: AI keeps running, modes only command AO.

        Kept as an explicit hook so the UI orchestration code is
        identical between the two providers (UI doesn't have to know
        which mode it is using).
        """
        return None

    def end_of_experiment(self) -> None:
        """No-op for the same reason as :meth:`arm_for_experiment`."""
        return None

    def peek_last(self, samples: int) -> np.ndarray:
        if not self._active:
            return np.empty((0, 0), dtype=float)
        return self._em.peek_last_samples(samples)

    def read_new(self, consumer_id: str) -> np.ndarray:
        if not self._active:
            return np.empty((0, 0), dtype=float)
        return self._em.read_new_samples(consumer_id)

    def is_active(self) -> bool:
        return self._active


__all__ = ["PersistentAIProvider"]
