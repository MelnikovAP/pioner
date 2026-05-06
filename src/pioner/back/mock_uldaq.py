"""Smart uldaq dispatcher.

If the real ``uldaq`` package is importable (and the underlying C library is
present), we re-export it directly. Otherwise we fall back to a small, *pure
Python* simulator that mimics enough of the API for development and tests on
machines without the MCC DAQ hardware.

Design decisions for the mock:

* **No security theatre.** The real ``uldaq`` does not have session tokens,
  rate limits, or operation-counters. Adding them here breaks long scans
  (status polling alone exceeds any throttle in seconds). The mock is a
  drop-in stub: same names, same shapes, no policy.
* **Shared buffer semantics.** The real driver fills the buffer in place via
  DMA. The mock implements the same: a worker thread mutates the actual list
  passed to :func:`a_in_scan`, so callers can poll ``buffer[i]`` and watch
  the data appear. Returning a copy from ``get_buffer`` would silently break
  the half-buffer reading loop in :class:`ExperimentManager`.
* **Index progression.** ``current_scan_count``/``current_index`` advance
  with wall-clock time so that loops which wait for a buffer to fill actually
  terminate.
* **Synthetic AI data.** When an AO scan is active, the mock derives a
  plausible AI signal: the temperature channel mirrors ``Theater(U_AO)`` of a
  default calibration with light Gaussian noise. This is good enough for
  end-to-end pipeline tests; it is **not** a thermal model of the chip.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Try the real uldaq first
# ---------------------------------------------------------------------------
try:  # pragma: no cover - presence depends on the host OS
    import uldaq as _real_uldaq  # type: ignore
    DAQ_AVAILABLE = True
    uldaq = _real_uldaq
    logger.info("Real uldaq detected, using actual DAQ hardware.")
except (ImportError, OSError) as exc:  # pragma: no cover - normal on dev hosts
    DAQ_AVAILABLE = False
    logger.info("uldaq not available (%s); using mock backend.", exc)

    # -----------------------------------------------------------------------
    # Enums (plain integers like in real uldaq)
    # -----------------------------------------------------------------------
    class InterfaceType:
        ANY = 7
        USB = 1
        BLUETOOTH = 2
        ETHERNET = 4

    class AiInputMode:
        DIFFERENTIAL = 1
        SINGLE_ENDED = 2

    class AInScanFlag:
        DEFAULT = 0

    class AOutScanFlag:
        DEFAULT = 0

    class ScanOption:
        DEFAULTIO = 0
        SINGLEIO = 1
        BLOCKIO = 2
        BURSTIO = 4
        CONTINUOUS = 8
        EXTCLOCK = 16
        EXTTRIGGER = 32
        RETRIGGER = 64

    class ScanStatus:
        IDLE = 0
        RUNNING = 1

    class TransferStatus:
        # Real uldaq exposes a class with attributes; we use it as a namespace
        # of constants for compatibility, but ``MockTransferStatus`` below is
        # what the mock returns from ``get_scan_status``.
        IDLE = 0
        RUNNING = 1

    class Range:
        BIP60VOLTS = 0
        BIP30VOLTS = 1
        BIP20VOLTS = 2
        BIP15VOLTS = 3
        BIP10VOLTS = 5

        def __init__(self, range_id: int):
            self.range_id = int(range_id)

        def __eq__(self, other) -> bool:
            return isinstance(other, Range) and other.range_id == self.range_id

        def __hash__(self) -> int:
            return hash(self.range_id)

        def __repr__(self) -> str:
            return f"Range({self.range_id})"

    class ULException(RuntimeError):
        """Mirror of ``uldaq.ULException`` for ``except`` blocks in user code."""

        def __init__(self, code: int = -1, message: str = "mock"):
            super().__init__(message)
            self.error_code = code
            self.error_message = message

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    def create_float_buffer(channel_count: int, samples_per_channel: int) -> List[float]:
        """Create a flat float buffer of size ``channels * samples_per_channel``."""
        if channel_count <= 0 or samples_per_channel <= 0:
            raise ValueError("channel_count and samples_per_channel must be > 0")
        return [0.0] * (channel_count * samples_per_channel)

    @dataclass
    class MockTransferStatus:
        current_scan_count: int = 0
        current_total_count: int = 0
        current_index: int = 0

    @dataclass
    class DaqDeviceDescriptor:
        product_name: str = "Mock DAQ Device"
        product_id: int = 0
        dev_interface: int = InterfaceType.USB
        dev_string: str = "Mock USB-DAQ"
        unique_id: str = "MOCK-0001"

    def get_daq_device_inventory(interface_type: int, max_devices: int = 1):
        if int(interface_type) not in {1, 2, 4, 7}:
            raise ValueError(f"Invalid interface_type {interface_type!r}")
        if max_devices <= 0:
            return []
        return [DaqDeviceDescriptor()]

    def get_net_daq_device_descriptor(host: str, port: int):
        if not host:
            raise ValueError("host must be a non-empty string")
        if not 1 <= int(port) <= 65535:
            raise ValueError("port must be in [1, 65535]")
        return DaqDeviceDescriptor()

    # -----------------------------------------------------------------------
    # Shared scan state, used by AI to pick up the latest AO voltages
    # -----------------------------------------------------------------------
    class _SharedScanState:
        """Glue between the AO and AI mocks living on the same DaqDevice."""

        def __init__(self) -> None:
            self.ao_buffer: Optional[List[float]] = None
            self.ao_low: int = 0
            self.ao_high: int = 0
            self.ao_rate: float = 0.0
            self.ao_start_time: float = 0.0
            self.ao_options: int = 0
            self.iso_voltages: dict[int, float] = {}

        def set_ao_scan(
            self,
            buffer: List[float],
            low: int,
            high: int,
            rate: float,
            options: int,
        ) -> None:
            self.ao_buffer = buffer
            self.ao_low = low
            self.ao_high = high
            self.ao_rate = float(rate)
            self.ao_start_time = time.monotonic()
            self.ao_options = int(options)

        def stop_ao(self) -> None:
            self.ao_buffer = None

        def voltage_at(self, channel: int, t: float) -> float:
            """Best-effort estimate of what the AO is outputting on ``channel``."""
            if channel in self.iso_voltages:
                return float(self.iso_voltages[channel])
            buf = self.ao_buffer
            if buf is None or self.ao_rate <= 0 or channel < self.ao_low or channel > self.ao_high:
                return 0.0
            n_chans = self.ao_high - self.ao_low + 1
            samples_per_chan = len(buf) // n_chans
            if samples_per_chan == 0:
                return 0.0
            elapsed = max(t - self.ao_start_time, 0.0)
            sample_index = int(elapsed * self.ao_rate)
            if self.ao_options & ScanOption.CONTINUOUS:
                sample_index %= samples_per_chan
            else:
                sample_index = min(sample_index, samples_per_chan - 1)
            offset = (channel - self.ao_low)
            return float(buf[sample_index * n_chans + offset])

    # -----------------------------------------------------------------------
    # AI / AO mock devices
    # -----------------------------------------------------------------------
    class _MockAiInfo:
        def get_num_chans_by_mode(self, mode: int) -> int:
            return 8

        def has_pacer(self) -> bool:
            return True

    class _MockAoInfo:
        def has_pacer(self) -> bool:
            return True

    class MockAiDevice:
        """Mock implementation of ``uldaq.AiDevice``."""

        def __init__(self, shared: _SharedScanState):
            self._shared = shared
            self._buffer: Optional[List[float]] = None
            self._lock = threading.RLock()
            self._stop_event = threading.Event()
            self._worker: Optional[threading.Thread] = None
            self._scan_count = 0
            self._total_count = 0
            self._current_index = 0
            self._rate = 0.0
            self._n_channels = 0
            self._low_channel = 0
            self._high_channel = 0
            self._continuous = False
            self._scanning = False

        # API used by AiDeviceHandler ----------------------------------
        def get_info(self) -> _MockAiInfo:
            return _MockAiInfo()

        def a_in_scan(
            self,
            low_channel: int,
            high_channel: int,
            input_mode: int,
            analog_range: Range,
            samples_per_channel: int,
            rate: float,
            options: int,
            flags: int,
            data: List[float],
        ) -> float:
            n_chans = high_channel - low_channel + 1
            expected = n_chans * samples_per_channel
            if len(data) < expected:
                raise ValueError(
                    f"buffer too small ({len(data)} < {expected} = "
                    f"{n_chans} channels * {samples_per_channel} samples)"
                )
            # Make sure no previous worker is still alive before we re-arm
            # ``_stop_event``. Without this join() a stale worker would keep
            # mutating the new buffer.
            self._terminate_worker()
            with self._lock:
                if self._scanning:
                    raise RuntimeError("AI scan already running")
                self._buffer = data
                self._rate = float(rate)
                self._n_channels = n_chans
                self._low_channel = low_channel
                self._high_channel = high_channel
                self._total_count = samples_per_channel
                self._scan_count = 0
                self._current_index = 0
                self._continuous = bool(options & ScanOption.CONTINUOUS)
                self._scanning = True
                self._stop_event.clear()
                self._worker = threading.Thread(
                    target=self._fill_loop, name="MockAiScan", daemon=True
                )
                self._worker.start()
            return float(rate)

        def _terminate_worker(self) -> None:
            """Stop the current background worker (if any) and wait for it."""
            self._stop_event.set()
            worker = self._worker
            if worker is not None and worker is not threading.current_thread():
                worker.join(timeout=1.0)
            self._worker = None

        def get_scan_status(self):
            with self._lock:
                status = ScanStatus.RUNNING if self._scanning else ScanStatus.IDLE
                return status, MockTransferStatus(
                    current_scan_count=self._scan_count,
                    current_total_count=self._total_count,
                    current_index=self._current_index,
                )

        @property
        def status(self) -> int:
            return self.get_scan_status()[0]

        def get_buffer(self) -> List[float]:
            # Real uldaq uses the very same buffer we received; do the same.
            return self._buffer if self._buffer is not None else []

        def scan_stop(self) -> None:
            self._terminate_worker()
            with self._lock:
                self._scanning = False

        # Internal worker ---------------------------------------------
        def _fill_loop(self) -> None:
            assert self._buffer is not None
            buf = self._buffer
            n_chans = self._n_channels
            buf_len = self._total_count  # samples per channel
            rate = max(self._rate, 1.0)
            chunk_samples = max(1, int(rate / 200))  # ~5 ms chunks at 20 kHz
            sample_period = 1.0 / rate

            scan_index = 0
            t_start = time.monotonic()
            while not self._stop_event.is_set():
                target_samples = int((time.monotonic() - t_start) / sample_period)
                if target_samples <= scan_index:
                    time.sleep(0.001)
                    continue
                end_index = min(target_samples, scan_index + chunk_samples)
                if not self._continuous and end_index >= buf_len:
                    end_index = buf_len
                for i in range(scan_index, end_index):
                    write_pos = i % buf_len
                    base_offset = write_pos * n_chans
                    sample_time = t_start + i * sample_period
                    for ch_idx in range(n_chans):
                        ch = self._low_channel + ch_idx
                        buf[base_offset + ch_idx] = self._synthesise_sample(ch, sample_time)
                with self._lock:
                    self._current_index = (end_index % buf_len) * n_chans
                    self._scan_count = end_index
                scan_index = end_index
                if not self._continuous and scan_index >= buf_len:
                    break
            with self._lock:
                self._scanning = False

        def _synthesise_sample(self, channel: int, t: float) -> float:
            """Cheap-but-plausible synthetic AI value derived from the AO state."""
            # Channel layout used by the experiment manager:
            #   0 = current shunt, 1 = Umod (high-gain), 2 = unused,
            #   3 = AD595 cold-junction, 4 = Utpl (thermopile),
            #   5 = Uhtr (heater voltage).
            base_voltage = self._shared.voltage_at(channel, t)
            noise = (math.sin(t * 1234.5 + channel) * 0.5e-3)  # deterministic ~0.5 mV noise

            if channel == 0:  # current
                # Crude V/R scaling to make the value non-zero.
                return base_voltage / 1700.0 + noise
            if channel == 5:  # heater voltage feedback
                return base_voltage + noise
            if channel == 4 or channel == 1:  # Utpl / Umod
                # Mock thermopile: maps AO 0..safe_voltage -> -0.05..0.05 V.
                return 0.005 * base_voltage + noise
            if channel == 3:  # AD595 ambient
                return 0.25 + noise  # ~25 °C
            return noise

    class MockAoDevice:
        """Mock implementation of ``uldaq.AoDevice``."""

        def __init__(self, shared: _SharedScanState):
            self._shared = shared
            self._lock = threading.RLock()
            self._scanning = False
            self._scan_count = 0
            self._total_count = 0
            self._current_index = 0
            self._scan_start = 0.0
            self._continuous = False

        def get_info(self) -> _MockAoInfo:
            return _MockAoInfo()

        def a_out(
            self,
            ao_channel: int,
            analog_range: Range,
            scan_flags: int,
            voltage: float,
        ) -> float:
            if ao_channel < 0:
                raise ValueError("ao_channel must be >= 0")
            self._shared.iso_voltages[int(ao_channel)] = float(voltage)
            self._shared.stop_ao()
            return float(voltage)

        def a_out_scan(
            self,
            low_channel: int,
            high_channel: int,
            analog_range: Range,
            samples_per_channel: int,
            rate: float,
            options: int,
            scan_flags: int,
            ao_buffer: List[float],
        ) -> float:
            n_chans = high_channel - low_channel + 1
            expected = n_chans * samples_per_channel
            if len(ao_buffer) != expected:
                raise ValueError(
                    f"AO buffer size {len(ao_buffer)} does not match "
                    f"{n_chans} channels * {samples_per_channel} samples"
                )
            with self._lock:
                self._shared.set_ao_scan(ao_buffer, low_channel, high_channel, rate, options)
                self._scanning = True
                self._scan_count = 0
                self._total_count = samples_per_channel
                self._current_index = 0
                self._scan_start = time.monotonic()
                self._continuous = bool(options & ScanOption.CONTINUOUS)
            # Iso voltages are no longer authoritative once a scan starts.
            for ch in range(low_channel, high_channel + 1):
                self._shared.iso_voltages.pop(ch, None)
            return float(rate)

        def scan_stop(self) -> None:
            with self._lock:
                self._scanning = False
                self._shared.stop_ao()

        def get_scan_status(self):
            with self._lock:
                if not self._scanning:
                    return ScanStatus.IDLE, MockTransferStatus()
                rate = self._shared.ao_rate or 1.0
                elapsed = time.monotonic() - self._scan_start
                samples = int(elapsed * rate)
                if not self._continuous and samples >= self._total_count:
                    samples = self._total_count
                    self._scanning = False
                self._scan_count = samples
                self._current_index = (samples % max(self._total_count, 1)) * (
                    self._shared.ao_high - self._shared.ao_low + 1
                )
                return ScanStatus.RUNNING if self._scanning else ScanStatus.IDLE, MockTransferStatus(
                    current_scan_count=self._scan_count,
                    current_total_count=self._total_count,
                    current_index=self._current_index,
                )

        @property
        def status(self) -> int:
            return self.get_scan_status()[0]

    # -----------------------------------------------------------------------
    # DaqDevice (high-level handle)
    # -----------------------------------------------------------------------
    class DaqDevice:
        def __init__(self, descriptor: DaqDeviceDescriptor):
            self._descriptor = descriptor
            self._connected = False
            self._shared = _SharedScanState()
            self._ai_device = MockAiDevice(self._shared)
            self._ao_device = MockAoDevice(self._shared)

        def get_descriptor(self) -> DaqDeviceDescriptor:
            return self._descriptor

        def is_connected(self) -> bool:
            return self._connected

        def connect(self, connection_code: int = -1) -> None:
            self._connected = True

        def disconnect(self) -> None:
            self._connected = False
            self._ai_device.scan_stop()
            self._ao_device.scan_stop()

        def release(self) -> None:
            self.disconnect()

        def reset(self) -> None:
            self.disconnect()

        def quit(self) -> None:
            self.disconnect()

        def get_ai_device(self) -> MockAiDevice:
            return self._ai_device

        def get_ao_device(self) -> MockAoDevice:
            return self._ao_device

    # -----------------------------------------------------------------------
    # Module-level shim that mirrors the ``uldaq`` namespace
    # -----------------------------------------------------------------------
    class _MockUldaqModule:
        InterfaceType = InterfaceType
        AiInputMode = AiInputMode
        AInScanFlag = AInScanFlag
        AOutScanFlag = AOutScanFlag
        ScanOption = ScanOption
        ScanStatus = ScanStatus
        TransferStatus = TransferStatus
        Range = Range
        DaqDeviceDescriptor = DaqDeviceDescriptor
        AiDevice = MockAiDevice
        AoDevice = MockAoDevice
        DaqDevice = staticmethod(lambda desc: DaqDevice(desc))
        ULException = ULException

        @staticmethod
        def get_daq_device_inventory(interface_type, max_devices=1):
            return get_daq_device_inventory(interface_type, max_devices)

        @staticmethod
        def get_net_daq_device_descriptor(host, port):
            return get_net_daq_device_descriptor(host, port)

        @staticmethod
        def create_float_buffer(channel_count, samples_per_channel):
            return create_float_buffer(channel_count, samples_per_channel)

    uldaq = _MockUldaqModule()


__all__ = ["uldaq", "DAQ_AVAILABLE"]
