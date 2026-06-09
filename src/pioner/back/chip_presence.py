"""Read-only chip-presence detection (P1-36).

Passive: inspects a window of raw AI samples (the thermopile channels are the
natural discriminators) and decides whether a chip is connected, WITHOUT driving
any AO. Physically this is an "open vs terminated input" test -- an open
thermopile input on a high-gain amp tends to rail or sit at a characteristic
offset, while a connected chip reads in a sane band.

The discriminating channel + threshold must be measured on the bench (chip in vs
out). Until then detection is config-gated and OFF by default (see
``ChipPresenceConfig.enabled``); three candidate strategies are provided so the
operator can compare them on real hardware via
``DeviceController.chip_presence_report()`` and pick one.

Strategies (each reads the configured channel's window statistics):

* ``band``      -- present iff ``mean`` is within ``[band_lo, band_hi]`` V
                   (open input drifts outside the operating band).
* ``abs_level`` -- present iff ``|mean| <= max_abs`` V (open input rails high).
* ``variance``  -- present iff ``std <= max_std`` V (open input is noisy).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from pioner.shared.settings import CHIP_PRESENCE_STRATEGIES, ChipPresenceConfig


@dataclass
class ChannelMetrics:
    """Window statistics for a single AI channel (all in volts)."""

    mean: float
    std: float
    min: float
    max: float
    p2p: float   # peak-to-peak = max - min


@dataclass
class ChipPresenceVerdict:
    present: bool
    reason: str


def channel_metrics(column) -> ChannelMetrics:
    """Compute window statistics for one channel column (1-D array of volts)."""
    a = np.asarray(column, dtype=float)
    lo = float(np.min(a))
    hi = float(np.max(a))
    return ChannelMetrics(
        mean=float(np.mean(a)),
        std=float(np.std(a)),
        min=lo,
        max=hi,
        p2p=hi - lo,
    )


def presence_metrics(window, channels) -> dict:
    """Per-channel :class:`ChannelMetrics` for a raw AI window.

    ``window`` is ``(samples, n_scanned_channels)``; ``channels`` is the AI
    channel index for each column, in column order (the controller's
    ``_ai_channels``). Returns ``{channel_index: ChannelMetrics}``. Empty / 1-D
    windows return ``{}``.
    """
    w = np.asarray(window, dtype=float)
    if w.ndim != 2 or w.size == 0:
        return {}
    out = {}
    for col, ch in enumerate(channels):
        if col >= w.shape[1]:
            break
        out[int(ch)] = channel_metrics(w[:, col])
    return out


def _verdict_band(m: ChannelMetrics, cfg: ChipPresenceConfig) -> ChipPresenceVerdict:
    present = cfg.band_lo <= m.mean <= cfg.band_hi
    return ChipPresenceVerdict(
        present,
        f"mean={m.mean:.4g} V {'within' if present else 'outside'} "
        f"band [{cfg.band_lo:g}, {cfg.band_hi:g}] V",
    )


def _verdict_abs_level(m: ChannelMetrics, cfg: ChipPresenceConfig) -> ChipPresenceVerdict:
    present = abs(m.mean) <= cfg.max_abs
    return ChipPresenceVerdict(
        present,
        f"|mean|={abs(m.mean):.4g} V {'<=' if present else '>'} "
        f"max_abs {cfg.max_abs:g} V",
    )


def _verdict_variance(m: ChannelMetrics, cfg: ChipPresenceConfig) -> ChipPresenceVerdict:
    present = m.std <= cfg.max_std
    return ChipPresenceVerdict(
        present,
        f"std={m.std:.4g} V {'<=' if present else '>'} max_std {cfg.max_std:g} V",
    )


_STRATEGY_FNS = {
    "band": _verdict_band,
    "abs_level": _verdict_abs_level,
    "variance": _verdict_variance,
}


def detect(metrics: dict, cfg: ChipPresenceConfig) -> ChipPresenceVerdict:
    """Apply the configured strategy to ``cfg.channel``'s metrics."""
    if cfg.strategy not in _STRATEGY_FNS:
        raise ValueError(
            f"unknown presence strategy {cfg.strategy!r} (one of {CHIP_PRESENCE_STRATEGIES})"
        )
    m = metrics.get(cfg.channel)
    if m is None:
        return ChipPresenceVerdict(False, f"channel {cfg.channel} not in the AI scan")
    return _STRATEGY_FNS[cfg.strategy](m, cfg)


def presence_report(window, channels, cfg: ChipPresenceConfig) -> dict:
    """Bench-comparison report: raw per-channel metrics + every strategy's verdict.

    Read-only. Lets the operator look at the numbers with a chip in vs out and
    pick the discriminating channel + strategy + threshold. JSON-serializable.
    """
    metrics = presence_metrics(window, channels)
    if not metrics:
        return {"available": False, "channel": cfg.channel, "metrics": {}, "verdicts": {}}
    verdicts = {}
    for name in CHIP_PRESENCE_STRATEGIES:
        v = detect(metrics, replace(cfg, strategy=name))
        verdicts[name] = {"present": v.present, "reason": v.reason}
    return {
        "available": True,
        "channel": cfg.channel,
        "configured_strategy": cfg.strategy,
        "metrics": {ch: vars(m) for ch, m in metrics.items()},
        "verdicts": verdicts,
    }
