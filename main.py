#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from time import sleep
from os import system
from sys import stdout
from math import pi, sin
import numpy as np
from uldaq import (get_daq_device_inventory, DaqDevice, InterfaceType, ScanStatus,
                   ScanOption, create_float_buffer)
from uldaq import AInScanFlag, AiInputMode
from uldaq import AOutScanFlag

def main():
    daq_device = None
    interface_type = InterfaceType.ANY
    sample_rate = 1000000 											# Hz
    samples_per_channel = sample_rate*2 
    scan_options = ScanOption.CONTINUOUS
    
    ai_device = None
    ai_range_index = 0									# Use the first supported range
    ai_low_channel = 0
    ai_high_channel = 0
    ai_flags = AInScanFlag.DEFAULT
    ai_status = ScanStatus.IDLE
    
    ao_device = None
    ao_low_channel = 0
    ao_high_channel = 0
    ao_range_index = 0									# Use the first supported range
    ao_scan_flags = AOutScanFlag.DEFAULT
    ao_status = ScanStatus.IDLE
    end_voltage = 1

    try:
        devices = get_daq_device_inventory(interface_type)
        number_of_devices = len(devices)
        if number_of_devices == 0:
            raise RuntimeError('Error: No DAQ devices found')
        daq_device = DaqDevice(devices[0])

        ai_device = daq_device.get_ai_device()
        ao_device = daq_device.get_ao_device()

        # Establish a connection to the DAQ device.
        descriptor = daq_device.get_descriptor()
        print('\nConnecting to', descriptor.dev_string, '- please wait...')
        daq_device.connect(connection_code=0)

        ai_input_mode = AiInputMode.SINGLE_ENDED
        ai_info = ai_device.get_info()
        ai_ranges = ai_info.get_ranges(ai_input_mode)
        ai_channel_count = ai_high_channel - ai_low_channel + 1
        ai_data = create_float_buffer(ai_channel_count, samples_per_channel)
        
        ao_info = ao_device.get_info()
        ao_ranges = ao_info.get_ranges()
        ao_channel_count = ao_high_channel - ao_low_channel + 1
        ao_data = create_float_buffer(ao_channel_count, samples_per_channel)

        volt_ramp = np.linspace(0, end_voltage, len(ao_data))
        for i in range(len(ao_data)):
            ao_data[i] = volt_ramp[i]

        print('    Samples per channel: ', samples_per_channel)
        print('    Rate: ', sample_rate, 'Hz')
        
        try:
            input('\nHit ENTER to continue\n')
        except (NameError, SyntaxError):
            pass

        system('clear')

        # Start the acquisition.
        ai_rate = ai_device.a_in_scan(ai_low_channel, ai_high_channel, ai_input_mode,
                                   ai_ranges[ai_range_index], samples_per_channel,
                                   sample_rate, scan_options, ai_flags, ai_data)
        ao_rate = ao_device.a_out_scan(ao_low_channel, ao_high_channel,
                                   ao_ranges[ao_range_index], samples_per_channel,
                                   sample_rate, scan_options, ao_scan_flags, ao_data)
        
        try:
            while True:
                try:
                    stdout.write('\033[1;1H')
                    # Get the status of the background operation
                    ai_status, ai_transfer_status = ai_device.get_scan_status()
                    ao_status, ao_transfer_status = ao_device.get_scan_status()  
                    
                    ai_index = ai_transfer_status.current_index
                    ao_index = ao_transfer_status.current_index
                    
                    print('Please enter CTRL + C to terminate the process\n')
                    print('Scan rate = ', '{:.6f}'.format(sample_rate), 'Hz\n')
                    print('AI channels to read: from ', ai_low_channel, 'to', ai_high_channel)
                    
                    print('AI currentTotalCount = ',
                          ai_transfer_status.current_total_count)
                    print('AI currentScanCount = ',
                          ai_transfer_status.current_scan_count)
                    print('AI currentIndex = ', ai_index, '\n')
                    print('AO channels for output: from ', ao_low_channel, 'to', ao_high_channel)
                    print('AO currentTotalCount = ',
                          ao_transfer_status.current_total_count)
                    print('AO currentScanCount = ',
                          ao_transfer_status.current_scan_count)
                    print('AO currentIndex = ', ao_index, '\n')
                    
                    stdout.flush()
                    
                    # Display the data.
                    for i in range(ai_channel_count):
                        stdout.write('\x1b[2K')
                        print('chan =',
                              i + ai_low_channel, ': ',
                              '{:.6f}'.format(ai_data[ai_index + i]))

                    sleep(0.1)
                except (ValueError, NameError, SyntaxError):
                    break
        except KeyboardInterrupt:
            pass

    except RuntimeError as error:
        print('\n', error)

    finally:
        if daq_device:
            # Stop the acquisition if it is still running.
            if ai_status == ScanStatus.RUNNING:
                ai_device.scan_stop()
            if ao_status == ScanStatus.RUNNING:
                ao_device.scan_stop()
            if daq_device.is_connected():
                daq_device.disconnect()
            daq_device.release()


if __name__ == '__main__':
    main()
