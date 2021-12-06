from uldaq import Range, AOutFlag

def Ao_connect(daq_device):
    ao_device = daq_device.get_ao_device()
    ao_info = ao_device.get_info()
    return(ao_device, ao_info)

def Ao_set_value(ao_device, ao_info):
    print('\nNumber of analog output channels: {}'.format(ao_info.get_num_chans()))
    channel = int(input('\n\tSelect analog output channel: '))
    value = float(input('\n\tOutput value: '))
    data = ao_device.a_out(channel, Range.BIP10VOLTS, AOutFlag.DEFAULT, data=value)
    print('\nChannel ', channel, ' was set to: ', value)
