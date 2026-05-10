"""Thin wrapper over ``uldaq.AiDevice``.

Two important details that differ from the previous implementation:

1. The buffer is sized **explicitly** from a ``samples_per_channel`` argument,
   and that exact value is also passed to ``a_in_scan``. Sizing the buffer
   with ``max(1000, sample_rate)`` while telling ``a_in_scan`` only
   ``sample_rate`` was a long-standing bug: at low rates the half-buffer
   reading loop would never trip the second-half branch.
2. We support both finite (``BLOCKIO`` / ``DEFAULTIO``) and continuous scans.
   For finite acquisitions the loop in :class:`ExperimentManager` waits for
   the scan to terminate; for continuous scans it polls ``current_index``.
"""

from __future__ import annotations

import logging
from typing import MutableSequence, Protocol, Tuple, cast

from .mock_uldaq import uldaq as ul

logger = logging.getLogger(__name__)


class _TransferStatus(Protocol):
    """Structural type for the transfer-status object returned by uldaq.

    Real ``uldaq.TransferStatus`` and the mock's ``MockTransferStatus`` both
    expose ``current_index`` (sample offset of the writer head in the AI
    buffer); the experiment manager only relies on that field.
    """

    current_index: int


class AiParams:
    """Mutable bag of analog-input parameters parsed from JSON or set manually."""

    def __init__(self) -> None:
        self.sample_rate: int = -1                 # Hz, samples/channel/second
        self.range_id: int = -1                    # uldaq.Range identifier
        self.low_channel: int = -1
        self.high_channel: int = -1
        self.input_mode: int = ul.AiInputMode.SINGLE_ENDED
        self.scan_flags: int = ul.AInScanFlag.DEFAULT
        self.options: int = ul.ScanOption.CONTINUOUS

    def __str__(self) -> str:  # pragma: no cover - debug only
        return str(vars(self))

    def channel_count(self) -> int:
        return self.high_channel - self.low_channel + 1


class AiDeviceHandler:
    """Wrap an ``uldaq.AiDevice`` and pre-allocate its read buffer."""

    def __init__(self, ai_device, params: AiParams):
        if ai_device is None:
            raise RuntimeError("DAQ device does not expose an AiDevice")

        self._ai_device = ai_device
        self._params = params
        # Real uldaq returns a ctypes Array[c_double], mock returns List[float];
        # both satisfy MutableSequence[float] (indexable, sliceable, len-able), which
        # is all the experiment manager needs.
        self._buffer: MutableSequence[float] = []
        self._buffer_samples_per_channel: int = 0

        info = ai_device.get_info()
        if not info.has_pacer():
            raise RuntimeError("AiDevice does not support hardware pacing")
        if info.get_num_chans_by_mode(ul.AiInputMode.SINGLE_ENDED) <= 0:
            self._params.input_mode = ul.AiInputMode.DIFFERENTIAL

    # ------------------------------------------------------------------
    # Buffer management
    # ------------------------------------------------------------------
    def allocate_buffer(self, samples_per_channel: int) -> MutableSequence[float]:
        """Allocate a buffer big enough for ``samples_per_channel`` samples per channel."""
        if samples_per_channel <= 0:
            raise ValueError("samples_per_channel must be > 0")
        n_chans = self._params.channel_count()
        if n_chans <= 0:
            raise ValueError("AI channel range is invalid")
        self._buffer_samples_per_channel = samples_per_channel
        # Real uldaq returns ctypes Array[c_double] (invariant, not a Sequence
        # subclass in stubs); the mock returns List[float]. Cast — both are
        # indexable/sliceable, which is all the experiment manager needs.
        self._buffer = cast(
            MutableSequence[float], ul.create_float_buffer(n_chans, samples_per_channel)
        )
        return self._buffer

    def get_buffer(self) -> MutableSequence[float]:
        return self._buffer

    @property
    def samples_per_channel(self) -> int:
        return self._buffer_samples_per_channel

    # ------------------------------------------------------------------
    # Scan control
    # ------------------------------------------------------------------
    def get(self):
        return self._ai_device

    def stop(self) -> None:
        try:
            self._ai_device.scan_stop()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("AI scan_stop failed: %s", exc)

    def status(self) -> Tuple[int, _TransferStatus]:
        return self._ai_device.get_scan_status()

    def scan(self, samples_per_channel: int | None = None) -> float:
        """Start an analog-input scan.

        If ``samples_per_channel`` is omitted, the previously allocated buffer
        size is used (this is the common path: AiDeviceHandler allocates the
        buffer, then ExperimentManager starts the scan).

        Re-allocates the buffer if the requested size differs from the
        currently allocated one — otherwise ``a_in_scan`` would silently scan
        into a too-small or too-large buffer.
        """
        if samples_per_channel is None:
            samples_per_channel = self._buffer_samples_per_channel
        if samples_per_channel <= 0:
            raise ValueError("AI buffer has not been allocated")
        if not self._buffer or samples_per_channel != self._buffer_samples_per_channel:
            self.allocate_buffer(samples_per_channel)

        analog_range = ul.Range(self._params.range_id)
        return self._ai_device.a_in_scan(
            self._params.low_channel,
            self._params.high_channel,
            self._params.input_mode,
            analog_range,
            samples_per_channel,
            self._params.sample_rate,
            self._params.options,
            self._params.scan_flags,
            self._buffer,
        )
