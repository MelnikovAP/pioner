"""Helpers that flatten per-channel voltage profiles into a single AO buffer.

The MCC DAQ ``a_out_scan`` expects an interleaved buffer where channel
samples cycle the fastest::

    [ch0_t0, ch1_t0, ..., chN_t0, ch0_t1, ch1_t1, ...]

This module contains two generators:

* :class:`ScanDataGenerator` — given a dictionary
  ``{"ch0": [...], "ch1": [...]}``, builds the interleaved buffer with the
  required channel range (unused channels are filled with zeros).
* :class:`PulseDataGenerator` — convenience generator for a constant per-
  channel voltage held for a fixed duration. Mostly historical; we keep it
  for the GUI's pulse demo.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, MutableSequence, cast

import numpy as np

from .mock_uldaq import uldaq as ul


def _channel_keys(low: int, high: int) -> List[str]:
    return [f"ch{i}" for i in range(low, high + 1)]


class ScanDataGenerator:
    """Build an AO buffer from a dict of per-channel voltage arrays."""

    def __init__(
        self,
        voltage_profiles: Dict[str, MutableSequence[float]],
        low_channel: int,
        high_channel: int,
    ) -> None:
        if low_channel > high_channel:
            raise ValueError("low_channel must be <= high_channel")
        if not voltage_profiles:
            raise ValueError("voltage_profiles is empty")

        lengths = {len(v) for v in voltage_profiles.values()}
        if len(lengths) > 1:
            raise ValueError(
                "Cannot build AO buffer: channel profiles have different lengths "
                f"({lengths})"
            )
        self._buffer_size = lengths.pop()
        if self._buffer_size <= 0:
            raise ValueError("Channel profiles must have at least one sample")

        self._low = low_channel
        self._high = high_channel
        self._n_chans = high_channel - low_channel + 1

        # Materialise dense channel arrays, defaulting absent ones to zeros.
        self._profiles: Dict[str, np.ndarray] = {}
        for key in _channel_keys(low_channel, high_channel):
            data = voltage_profiles.get(key)
            if data is None:
                self._profiles[key] = np.zeros(self._buffer_size, dtype=float)
            else:
                arr = np.asarray(data, dtype=float)
                if arr.ndim != 1:
                    raise ValueError(f"Profile '{key}' must be 1-D")
                self._profiles[key] = arr

        # Reject unknown channels early so the user sees a clear error.
        unknown = set(voltage_profiles) - set(self._profiles)
        if unknown:
            raise ValueError(
                f"voltage_profiles contains channels outside [{low_channel}, "
                f"{high_channel}]: {sorted(unknown)}"
            )

        self._buffer = self._build_buffer()

    def _build_buffer(self) -> MutableSequence[float]:
        # Real uldaq returns ctypes Array[c_double]; mock returns List[float].
        # Both support indexing/slicing, which is all the consumers need.
        buf = cast(MutableSequence[float], ul.create_float_buffer(self._n_chans, self._buffer_size))
        # Build the interleaved buffer in numpy, then push it into ``buf``.
        # ``buf`` is a Python list (mock) or a ctypes float array (real
        # uldaq); both support slice assignment from a Python list.
        matrix = np.column_stack([
            self._profiles[k] for k in _channel_keys(self._low, self._high)
        ])  # shape: (samples, channels)
        flat = matrix.reshape(-1).tolist()
        try:
            buf[:] = flat
        except (TypeError, ValueError):
            # Older ctypes arrays may not accept full-slice assignment;
            # fall back to per-element assignment.
            for i, value in enumerate(flat):
                buf[i] = float(value)
        return buf

    def get_buffer(self) -> MutableSequence[float]:
        return self._buffer


class PulseDataGenerator:
    """Hold a constant per-channel voltage for ``duration`` samples."""

    def __init__(
        self,
        channel_voltages: Dict[str, float],
        duration: int,
        low_channel: int,
        high_channel: int,
    ) -> None:
        if duration <= 0:
            raise ValueError("duration must be > 0 samples")
        flat: Dict[str, MutableSequence[float]] = {}
        for key in _channel_keys(low_channel, high_channel):
            value = float(channel_voltages.get(key, 0.0))
            flat[key] = [value] * duration
        self._inner = ScanDataGenerator(flat, low_channel, high_channel)

    def get_buffer(self) -> MutableSequence[float]:
        return self._inner.get_buffer()


__all__ = ["ScanDataGenerator", "PulseDataGenerator"]
