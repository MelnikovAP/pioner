from scan_params import ScanParams
from ao_params import AoParams

import uldaq as ul
import math


class AoDeviceHandler:
    def __init__(self, ao_device_from_daq: ul.AoDevice,
                 params: AoParams, scan_params: ScanParams):
        self._ao_device = ao_device_from_daq
        self._params = params
        self._scan_params = scan_params

        if self._ao_device is None:
            raise RuntimeError("Error. DAQ device doesn't support analog output.")

        info = self._ao_device.get_info()
        if not info.has_pacer():
            raise RuntimeError("Error. DAQ device doesn't support hardware paced analog output.")

        channel_count = self._params.high_channel - self._params.low_channel + 1
        self._buffer = ul.create_float_buffer(channel_count, self._scan_params.samples_per_channel)
        self._fill_buffer()

    def get(self) -> ul.AoDevice:
        return self._ao_device

    # returns actual output scan rate
    def scan(self) -> float:
        info = self._ao_device.get_info()
        analog_ranges = info.get_ranges()
        if self._params.range_id >= len(analog_ranges):
            self._params.range_id = len(analog_ranges) - 1

        analog_range = analog_ranges[self._params.range_id]
        return self._ao_device.a_out_scan(self._params.low_channel, self._params.high_channel,
                                          analog_range, self._scan_params.samples_per_channel,
                                          self._scan_params.sample_rate, self._scan_params.options, 
                                          self._params.scan_flags, self._buffer)

    def _fill_buffer(self):
        amplitude = 1.0  # Volts
        # Set an offset if the range is unipolar
        offset = amplitude if self._params.range_id > 1000 else 0.0
        samples_per_cycle = int(self._scan_params.sample_rate / 10.0)  # 10 Hz sine wave        
        cycles_per_buffer = int(self._scan_params.samples_per_channel / samples_per_cycle)
        i = 0
        for _cycle in range(cycles_per_buffer):
            for sample in range(samples_per_cycle):
                for _chan in range(self._scan_params.channel_count):
                    self._buffer[i] = amplitude * math.sin(2 * math.pi * sample / samples_per_cycle) + offset
                    i += 1
