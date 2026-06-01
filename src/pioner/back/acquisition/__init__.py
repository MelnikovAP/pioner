"""AI acquisition abstraction layer.

This package owns the lifecycle of the AI scan separately from the
experiment modes (FastHeat / SlowMode / IsoMode / Calibration). It
exposes a single :class:`AIProvider` interface with two interchangeable
implementations selected at runtime by the ``AcquisitionMode`` field of
``settings.json``:

* :class:`PersistentAIProvider` (default) -- one AI scan started at
  ``Connect`` and stopped at ``Disconnect``. All readers (UI Values
  sidebar, slow-heat / iso live plots, future disk recorder) share the
  same ring buffer via per-consumer cursors. Experiment modes only
  command AO.
* :class:`PerExperimentAIProvider` -- the legacy shape where each
  experiment arms its own AI scan and a separate monitoring AI session
  runs between experiments. Preserved as an alternative for empirical
  validation (see ``docs/live-streaming.md`` section 13.4).

The shared :func:`create_ai_provider` factory picks the right
implementation based on a config string ("persistent" or
"per_experiment").

Design rationale: ``docs/live-streaming.md`` section 3.
"""

from pioner.back.acquisition.base import AIProvider, AcquisitionMode
from pioner.back.acquisition.persistent import PersistentAIProvider
from pioner.back.acquisition.per_experiment import PerExperimentAIProvider
from pioner.back.acquisition.factory import create_ai_provider

__all__ = [
    "AIProvider",
    "AcquisitionMode",
    "PersistentAIProvider",
    "PerExperimentAIProvider",
    "create_ai_provider",
]
