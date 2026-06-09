"""In-memory tally of operator actions during one GUI session (P1-40, MVP).

Deliberately minimal: a counter of discrete events plus a one-line
:meth:`SessionStats.summary` logged when the session ends. It answers basic
"what happened this session" questions -- how many experiments ran, how many
were aborted, how many programs were rejected, connect churn -- without any
timing/persistence machinery. A richer stats/telemetry pipeline (per-run
timings + metadata, on-disk history, aggregation across sessions) is future
work; see TODO P1-41.

Pure (no Qt / no DAQ) so it is unit-testable on its own.
"""

from __future__ import annotations

from collections import Counter

# Event keys (use the constants, not literals, at call sites to avoid typos).
CONNECT = "connect"
ARM = "arm"
ARM_REJECTED = "arm_rejected"
RUN_STARTED = "run_started"
RUN_FINISHED = "run_finished"
STOP = "stop"
ISO_SET = "iso_set"
ISO_OFF = "iso_off"
CHIP_CHECK = "chip_check"
SETTINGS_SAVED = "settings_saved"


class SessionStats:
    """Counts discrete operator actions; renders a digest at session end."""

    def __init__(self) -> None:
        self._counts: Counter = Counter()

    def record(self, event: str, n: int = 1) -> None:
        self._counts[event] += n

    def get(self, event: str) -> int:
        return self._counts[event]

    def as_dict(self) -> dict:
        return dict(self._counts)

    def summary(self) -> str:
        """One-line digest, e.g. ``session stats: arm=3, run_finished=2, stop=1``."""
        if not self._counts:
            return "session stats: (no recorded actions)"
        parts = ", ".join(f"{k}={v}" for k, v in sorted(self._counts.items()))
        return f"session stats: {parts}"
