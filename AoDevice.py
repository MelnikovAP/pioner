from uldaq import Range, AOutScanFlag, ScanStatus

def Ao_connect(daq_device):
    return(daq_device.get_ao_device())
    
def Ao_get_info(ao_device):
    ao_info = ao_device.get_info()
    return({'Channels number':ao_info.get_num_chans(),
            'Ranges':ao_info.get_ranges()
        })

def Ao_set_value(ao_device, ao_info):
    print('\nNumber of analog output channels: {}'.format(ao_info.get_num_chans()))
    channel = int(input('\n\tSelect analog output channel: '))
    value = float(input('\n\tOutput value: '))
    data = ao_device.a_out(channel, Range.BIP10VOLTS, AOutScanFlag.DEFAULT, data=value)
    print('\nChannel ', channel, ' was set to: ', value)
