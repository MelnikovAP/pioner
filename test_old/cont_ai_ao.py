#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from time import sleep
from os import system
from sys import stdout
from math import pi, sin
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

    try:
        # Get descriptors for all of the available DAQ devices.
        devices = get_daq_device_inventory(interface_type)
        number_of_devices = len(devices)
        if number_of_devices == 0:
            raise RuntimeError('Error: No DAQ devices found')

        print('Found', number_of_devices, 'DAQ device(s):')
        for i in range(number_of_devices):
            print('  [', i, '] ', devices[i].product_name, ' (',
                  devices[i].unique_id, ')', sep='')

        descriptor_index = input('\nPlease select a DAQ device, enter a number'
                                 + ' between 0 and '
                                 + str(number_of_devices - 1) + ': ')
        descriptor_index = int(descriptor_index)
        if descriptor_index not in range(number_of_devices):
            raise RuntimeError('Error: Invalid descriptor index')

        # Create the DAQ device from the descriptor at the specified index.
        daq_device = DaqDevice(devices[descriptor_index])

        # Get the AiDevice and AoDevice objects and verify that it is valid.
        ai_device = daq_device.get_ai_device()
        if ai_device is None:
            raise RuntimeError('Error: The DAQ device does not support analog '
                               'input')
        ao_device = daq_device.get_ao_device()
        if ao_device is None:
            raise RuntimeError('Error: The DAQ device does not support analog '
                               'output')

        # Verify the specified device supports hardware pacing for analog input and output.
        ai_info = ai_device.get_info()
        if not ai_info.has_pacer():
            raise RuntimeError('\nError: The specified DAQ device does not '
                               'support hardware paced analog input')
        ao_info = ao_device.get_info()
        if not ao_info.has_pacer():
            raise RuntimeError('Error: The DAQ device does not support paced '
                               'analog output')

        # Establish a connection to the DAQ device.
        descriptor = daq_device.get_descriptor()
        print('\nConnecting to', descriptor.dev_string, '- please wait...')
        # For Ethernet devices using a connection_code other than the default
        # value of zero, change the line below to enter the desired code.
        daq_device.connect(connection_code=0)

        # The default input mode is SINGLE_ENDED.
        ai_input_mode = AiInputMode.SINGLE_ENDED
        # If SINGLE_ENDED input mode is not supported, set to DIFFERENTIAL.
        if ai_info.get_num_chans_by_mode(AiInputMode.SINGLE_ENDED) <= 0:
            ai_input_mode = AiInputMode.DIFFERENTIAL

        # Get the number of channels and validate the high channel number.
        ai_channel_count = ai_high_channel - ai_low_channel + 1
        ao_channel_count = ao_high_channel - ao_low_channel + 1

        # Get a list of supported ranges and validate the range index.
        ai_ranges = ai_info.get_ranges(ai_input_mode)
        if ai_range_index >= len(ai_ranges):
            ai_range_index = len(ai_ranges) - 1
            
        ao_ranges = ao_info.get_ranges()
        if ao_range_index >= len(ao_ranges):
            ao_range_index = len(ao_ranges) - 1

        # Allocate buffers to receive and push the data.
        ai_data = create_float_buffer(ai_channel_count, samples_per_channel)
        ao_data = create_float_buffer(ao_channel_count, samples_per_channel)
        
        # Fill the output buffer with data.
        amplitude = 1.0  # Volts
        # Set an offset if the range is unipolar
        offset = amplitude if ao_range_index > 1000 else 0.0
        samples_per_cycle = int(sample_rate / 10.0)  # 10 Hz sine wave
        create_output_data(ao_channel_count, samples_per_channel, samples_per_cycle,
                           amplitude, offset, ao_data)

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
                    reset_cursor()
                    # Get the status of the background operation
                    ai_status, ai_transfer_status = ai_device.get_scan_status()
                    ao_status, ao_transfer_status = ao_device.get_scan_status()  
                    
                    if ai_status != ScanStatus.RUNNING:
                        break
                    if ao_status != ScanStatus.RUNNING:
                        break
                    
                    ai_index = ai_transfer_status.current_index
                    ao_index = ao_transfer_status.current_index
                    
                    print('Please enter CTRL + C to terminate the process\n')
                    print('Active DAQ device: ', descriptor.dev_string, ' (',
                           descriptor.unique_id, ')\n', sep='')
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
                        clear_eol()
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


def create_output_data(number_of_channels, samples_per_channel,
                       samples_per_cycle, amplitude, offset, data_buffer):
    """Populate the buffer with sine wave data for the specified number of
       channels."""
    cycles_per_buffer = int(samples_per_channel / samples_per_cycle)
    i = 0
    for _cycle in range(cycles_per_buffer):
        for sample in range(samples_per_cycle):
            for _chan in range(number_of_channels):
                data_buffer[i] = amplitude * sin(2 * pi * sample
                                                 / samples_per_cycle) + offset
                i += 1

def reset_cursor():
    """Reset the cursor in the terminal window."""
    stdout.write('\033[1;1H')
    
def clear_eol():
    """Clear all characters to the end of the line."""
    stdout.write('\x1b[2K')


if __name__ == '__main__':
    main()
