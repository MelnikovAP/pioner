from uldaq import DaqDevice, get_daq_device_inventory, InterfaceType
from time import sleep

def DD_list():
    return(get_daq_device_inventory(InterfaceType.USB))

def DD_connect(device_list):   
    # Create a DaqDevice Object and connect to the device 
    daq_device = DaqDevice(device_list[0]) 
    daq_device.connect() 
    return(daq_device)
 
def DD_flash_led(daq_device, counts=1, interval=1, duration=1):
    for i in range(counts): 
        daq_device.flash_led(duration) 
        sleep(interval) 
    
def DD_get_info(daq_device):
    daq_descriptor = daq_device.get_descriptor() 
    return({'name':daq_descriptor.product_name, 
            'id':daq_descriptor.product_id, 
            'unique id':daq_descriptor.unique_id}) 

def DD_disconnect(daq_device):
    daq_device.disconnect()
    daq_device.release()
