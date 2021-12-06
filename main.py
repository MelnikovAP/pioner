from DaqBoard import DD_connect, DD_flash_led, DD_print_info
from AiDevice import Ai_connect, Ai_cont_scan
from AoDevice import Ao_connect, Ao_set_value
from uldaq import InterfaceType, get_daq_device_inventory, ULException
from os import system

operation_modes = {
                   1: 'Continious analog input scan',
                   2: 'Continious analog output scan',
                   3: 'Single analog input scan',
                  }



try:
    # Get a list of available DAQ devices
    device_list = get_daq_device_inventory(InterfaceType.USB)
    number_of_devices = len(device_list)
    if number_of_devices == 0:
        raise RuntimeError('!!! Error: No DAQ devices found !!!')
    system('clear')
   
    daq_device = DD_connect(device_list)
    DD_flash_led(daq_device)
    DD_print_info(daq_device)

    try:
        print('\n\t====================================')
        print('\tAvailable operation modes:')
        for key, value in operation_modes.items():
            print('\t', key, ' : ', value) 
        ans = int(input('\n\tSelect the mode\n'))
    except (NameError, SyntaxError):
        pass

    if ans == 1:
        ai_device, ai_info = Ai_connect(daq_device)
        Ai_cont_scan(ai_device, ai_info)

except ULException as e:
    print('\n', e)  # Display any error messages

