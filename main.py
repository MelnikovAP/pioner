from DaqBoard import *
from AiDevice import *
from AoDevice import *
from uldaq import ULException
from os import system
from sys import stdout
import numpy as np


try:
    # Get a list of available DAQ devices and connecting to it
    device_list = DD_list()
    if device_list == 0:
        raise RuntimeError('!!! Error: No DAQ devices found !!!')
    system('clear')

    daq_device = DD_connect(device_list)
    device_info = DD_get_info(daq_device)
    print('DAQ board model :', device_info['name'])
    DD_flash_led(daq_device, 1,1,1)

    # Launching continuous scan and reading the data on AI device
    channel = 1
    sample_rate = 10000

    ai_device = Ai_connect(daq_device)
    Ai_cont_scan(ai_device, channel=channel, 
                            sample_rate=sample_rate)

except ULException as e:
    print('\n', e)  # Display any error messages

