"""Tests for the per-session action tally (P1-40 MVP)."""

from pioner.shared import session_stats as stats
from pioner.shared.session_stats import SessionStats


def test_empty_summary():
    assert SessionStats().summary() == "session stats: (no recorded actions)"


def test_record_counts_and_get():
    s = SessionStats()
    s.record(stats.ARM)
    s.record(stats.ARM)
    s.record(stats.RUN_STARTED, 3)
    assert s.get(stats.ARM) == 2
    assert s.get(stats.RUN_STARTED) == 3
    assert s.get(stats.STOP) == 0          # never recorded -> 0
    assert s.as_dict() == {stats.ARM: 2, stats.RUN_STARTED: 3}


def test_summary_is_sorted_and_readable():
    s = SessionStats()
    s.record(stats.STOP)
    s.record(stats.ARM)
    # keys sorted alphabetically -> deterministic line
    assert s.summary() == "session stats: arm=1, stop=1"
