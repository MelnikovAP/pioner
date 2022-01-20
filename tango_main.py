from DaqBoard import DD_connect, DD_flash_led, DD_get_info
from AiDevice import Ai_connect, Ai_get_info, Ai_cont_scan
from uldaq import InterfaceType, get_daq_device_inventory, ULException
import numpy as np
from os import system


def connect():
    # Get a list of available DAQ devices
    device_list = get_daq_device_inventory(InterfaceType.USB)
    number_of_devices = len(device_list)
    if number_of_devices == 0:
        raise RuntimeError('!!! Error: No DAQ devices found !!!')
    system('clear')

    daq_device = DD_connect(device_list)
    if daq_device.is_connected():
        print('DaqDevice has been connected')
    
    DD_flash_led(daq_device, 3, 1, 1)
    
    return(daq_device)

def tpl_scan(daq_device):
    data = np.array([])
    ai_device = Ai_connect(daq_device)

    try:
        input('\nHit ENTER to continue\n')
        Ai_cont_scan(data, ai_device, [0], 10, 1)
    except (NameError, SyntaxError):
        pass

#try:
#    daq_device = connect()
#    tpl_scan(daq_device)

#except ULException as e:
#    print('\n', e)  # Display any error messages

