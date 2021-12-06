from uldaq import DaqDevice
from time import sleep

def DD_connect(device_list):   
    # Create a DaqDevice Object and connect to the device 
    daq_device = DaqDevice(device_list[0]) 
    daq_device.connect() 
 
    if daq_device.is_connected(): 
        print('''
        ====================================
        ============= connected ============ 
        ==================================== 
              ''') 
    return(daq_device)
 
def DD_flash_led(daq_device):
    # Flashing the light 3 times in a row 
    for i in range(1): 
        daq_device.flash_led(1) 
        sleep(1) 
    
def DD_print_info(daq_device):
    daq_descriptor = daq_device.get_descriptor() 
    print('\tDAQ board model: {}'.format(daq_descriptor.product_name)) 
    print('\tDAQ board id: {}'.format(daq_descriptor.product_id)) 
    print('\tUnique id: {}'.format(daq_descriptor.unique_id)) 

def DD_disconnect(daq_device):
    daq_device.disconnect()
    daq_device.release()
    print('\n\tNow you can disconnect the DAQ board. Exiting script in 3 sec')
    sleep(3)
