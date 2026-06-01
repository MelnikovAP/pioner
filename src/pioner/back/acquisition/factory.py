"""Factory that picks the AIProvider implementation from a config string.

Calling code (GUI or Tango server) reads the ``AcquisitionMode`` field
from ``settings.json`` and passes the string here. Unknown / missing
values fall back to ``persistent`` (the documented default).
"""

from __future__ import annotations

import logging

from pioner.back.acquisition.base import AIProvider, AcquisitionMode
from pioner.back.acquisition.persistent import PersistentAIProvider
from pioner.back.acquisition.per_experiment import PerExperimentAIProvider
from pioner.back.experiment_manager import ExperimentManager

logger = logging.getLogger(__name__)


def create_ai_provider(
    mode: str | AcquisitionMode | None,
    em: ExperimentManager,
    ring_max_seconds: float = 2.0,
) -> AIProvider:
    """Construct the appropriate :class:`AIProvider` for the given mode.

    Parameters
    ----------
    mode
        ``"persistent"`` or ``"per_experiment"`` (string from
        ``settings.json``), or an :class:`AcquisitionMode` instance. Any
        other value falls back to PERSISTENT with a warning.
    em
        The owning :class:`ExperimentManager` (shared with the mode
        classes; the provider attaches its ring buffer to ``em``'s).
    ring_max_seconds
        Depth of in-RAM history.
    """
    if isinstance(mode, AcquisitionMode):
        acq_mode = mode
    else:
        acq_mode = AcquisitionMode.from_string(mode if isinstance(mode, str) else None)

    if acq_mode is AcquisitionMode.PERSISTENT:
        logger.info("Using PersistentAIProvider (AcquisitionMode='persistent')")
        return PersistentAIProvider(em, ring_max_seconds=ring_max_seconds)
    if acq_mode is AcquisitionMode.PER_EXPERIMENT:
        logger.info("Using PerExperimentAIProvider (AcquisitionMode='per_experiment')")
        return PerExperimentAIProvider(em, ring_max_seconds=ring_max_seconds)

    # Defensive: AcquisitionMode.from_string already normalised; this
    # branch is essentially unreachable but keeps type checkers happy.
    logger.warning("Unknown AcquisitionMode %r; falling back to persistent", mode)
    return PersistentAIProvider(em, ring_max_seconds=ring_max_seconds)


__all__ = ["create_ai_provider"]
