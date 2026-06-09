"""Pure-logic tests for read-only chip-presence detection (P1-36).

The detection strategies are pure functions over a raw AI window, so they are
tested with synthetic windows (no DAQ). The controller-level wiring (report on
the live mock ring, disabled -> None) is exercised in
``test_device_controller``-style checks at the bottom.
"""

import numpy as np
import pytest

from pioner.back.chip_presence import (
    channel_metrics,
    detect,
    presence_metrics,
    presence_report,
)
from pioner.shared.settings import ChipPresenceConfig


def test_channel_metrics_basic():
    m = channel_metrics([0.0, 2.0, 4.0])
    assert m.mean == 2.0
    assert m.min == 0.0 and m.max == 4.0
    assert m.p2p == 4.0
    assert m.std == pytest.approx(np.std([0.0, 2.0, 4.0]))


def test_presence_metrics_maps_channels_by_column_order():
    # window columns correspond to channels [0, 1, 4] in that order.
    window = np.array([[0.1, 5.0, -3.0], [0.3, 5.0, -3.0]])
    metrics = presence_metrics(window, [0, 1, 4])
    assert set(metrics) == {0, 1, 4}
    assert metrics[1].mean == 5.0
    assert metrics[4].mean == -3.0


def test_presence_metrics_empty_window():
    assert presence_metrics(np.empty((0, 0)), [0, 1]) == {}


def _metrics(channel, **stats):
    """Build a metrics dict with one channel from explicit stats."""
    col = stats["samples"]
    return presence_metrics(np.asarray(col, dtype=float).reshape(-1, 1), [channel])


def test_detect_band():
    cfg = ChipPresenceConfig(channel=4, strategy="band", band_lo=-1.0, band_hi=1.0)
    present = _metrics(4, samples=[0.0, 0.1, -0.1])      # mean ~0 -> in band
    absent = _metrics(4, samples=[9.9, 10.0, 9.8])        # mean ~9.9 -> out of band
    assert detect(present, cfg).present is True
    assert detect(absent, cfg).present is False


def test_detect_abs_level():
    cfg = ChipPresenceConfig(channel=4, strategy="abs_level", max_abs=1.0)
    assert detect(_metrics(4, samples=[0.2, -0.2]), cfg).present is True   # |mean| small
    assert detect(_metrics(4, samples=[9.0, 9.0]), cfg).present is False   # railed high


def test_detect_variance():
    cfg = ChipPresenceConfig(channel=4, strategy="variance", max_std=0.5)
    assert detect(_metrics(4, samples=[0.0, 0.01, -0.01]), cfg).present is True   # quiet
    assert detect(_metrics(4, samples=[-5.0, 5.0, -5.0, 5.0]), cfg).present is False  # noisy


def test_detect_unknown_strategy_raises():
    cfg = ChipPresenceConfig(strategy="band")
    object.__setattr__(cfg, "strategy", "bogus")   # bypass parse-time validation
    with pytest.raises(ValueError):
        detect(_metrics(4, samples=[0.0]), cfg)


def test_detect_channel_not_in_scan():
    cfg = ChipPresenceConfig(channel=99, strategy="band")
    verdict = detect(_metrics(4, samples=[0.0]), cfg)
    assert verdict.present is False
    assert "not in the AI scan" in verdict.reason


def test_presence_report_structure():
    window = np.array([[0.0, 0.1, 0.0, 0.0, 0.05, 0.0]] * 4)   # 6 channels
    cfg = ChipPresenceConfig(channel=4, strategy="band", band_lo=-1.0, band_hi=1.0)
    report = presence_report(window, [0, 1, 2, 3, 4, 5], cfg)
    assert report["available"] is True
    assert report["channel"] == 4
    assert set(report["verdicts"]) == {"band", "abs_level", "variance"}
    assert set(report["metrics"]) == {0, 1, 2, 3, 4, 5}
    assert report["verdicts"]["band"]["present"] is True


def test_presence_report_empty_window():
    report = presence_report(np.empty((0, 0)), [0, 1], ChipPresenceConfig())
    assert report["available"] is False
    assert report["metrics"] == {}
