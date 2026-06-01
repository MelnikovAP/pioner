"""Common interface for AI acquisition providers.

The two concrete providers (:class:`PersistentAIProvider`,
:class:`PerExperimentAIProvider`) differ in WHEN the AI scan starts
and stops, but expose the same surface to UI widgets and experiment
modes. Keeping the interface narrow is what makes them swappable
behind a config flag without ripple effects elsewhere.
"""

from __future__ import annotations

import abc
import enum
from typing import Sequence

import numpy as np


class AcquisitionMode(str, enum.Enum):
    """Valid values for the ``AcquisitionMode`` settings field."""

    PERSISTENT = "persistent"
    PER_EXPERIMENT = "per_experiment"

    @classmethod
    def from_string(cls, value: str | None) -> "AcquisitionMode":
        """Lenient parser used by :func:`create_ai_provider`.

        Falls back to PERSISTENT for missing / unknown values rather than
        raising -- the default is documented as ``persistent`` and missing
        the field should not break Connect.
        """
        if not value:
            return cls.PERSISTENT
        try:
            return cls(value.strip().lower())
        except ValueError:
            return cls.PERSISTENT


class AIProvider(abc.ABC):
    """Lifecycle + data-access contract for AI streaming.

    Lifecycle hooks (called by the GUI / Tango layer, never by modes):

    * :meth:`on_connect` -- DAQ has just been opened; provider may arm
      its AI scan.
    * :meth:`on_disconnect` -- DAQ is about to be released; provider
      must stop its AI scan and free any worker threads.
    * :meth:`arm_for_experiment` -- a real experiment mode is about to
      run. The persistent provider does nothing here (AI keeps running);
      the per-experiment provider tears down its monitoring scan so the
      mode can claim AI.
    * :meth:`end_of_experiment` -- the experiment mode is done. The
      persistent provider does nothing; the per-experiment provider
      restarts its monitoring scan.

    Data access (called by UI widgets and the future disk recorder):

    * :meth:`peek_last` -- "give me the most recent N samples". Read-only,
      does not advance any cursor. Used by the sliding-window demod on
      every UI tick.
    * :meth:`read_new` -- "give me everything since my last call". Each
      caller passes a unique ``consumer_id``; the provider tracks one
      cursor per id. Used by the disk recorder.

    Implementations MUST be safe to call from the Qt main thread (peek /
    read_new); the underlying ring buffer is locked appropriately by
    ``ExperimentManager``.
    """

    @abc.abstractmethod
    def on_connect(self, ai_channels: Sequence[int]) -> None:
        """Initialise the AI side after the DAQ has been opened."""

    @abc.abstractmethod
    def on_disconnect(self) -> None:
        """Stop and tear down any AI workers; safe to call multiple times."""

    @abc.abstractmethod
    def arm_for_experiment(self) -> None:
        """Hook invoked just before a mode's ``arm()`` / ``run()``."""

    @abc.abstractmethod
    def end_of_experiment(self) -> None:
        """Hook invoked just after a mode finishes (success or failure)."""

    @abc.abstractmethod
    def peek_last(self, samples: int) -> np.ndarray:
        """Return the most recent ``samples`` rows from the ring buffer.

        Does not advance any cursor. Returns an empty 2-D array if the
        AI scan is not active or fewer than ``samples`` are available.
        """

    @abc.abstractmethod
    def read_new(self, consumer_id: str) -> np.ndarray:
        """Return everything appended to the ring since the consumer's previous call.

        Advances the consumer's private cursor. The first call for a
        given ``consumer_id`` returns whatever is currently in the ring
        (the consumer joins at the current head).
        """

    # ------------------------------------------------------------------
    # Optional introspection -- default implementations are conservative
    # so subclasses only override when they have something meaningful to
    # report.
    # ------------------------------------------------------------------
    def is_active(self) -> bool:
        """``True`` when an AI scan is currently running."""
        return False

    @property
    def mode(self) -> AcquisitionMode:
        """Identifier for diagnostics / logging."""
        raise NotImplementedError


__all__ = ["AIProvider", "AcquisitionMode"]
