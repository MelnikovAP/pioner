from time import sleep
import uldaq as ul
               
try:
    # Get a list of available DAQ devices
    devices = ul.get_daq_device_inventory(ul.InterfaceType.USB)

    # Create a DaqDevice Object and connect to the device
    daq_device = ul.DaqDevice(devices[0])
    daq_device.connect()
    if daq_device.is_connected(): print('connected')
    else: print('disconnected') 

    # Flashing the light 3 times in a row
    for i in range(1):
        daq_device.flash_led(1)
        sleep(1)
    daq_descriptor = daq_device.get_descriptor() 
    print('DAQ board model: {}'.format(daq_descriptor.product_name))
    print('DAQ board id: {}'.format(daq_descriptor.product_id) + \
          ';    unique id: {}'.format(daq_descriptor.unique_id))

    # Get AiDevice and AiInfo objects for the analog input subsystem
    ai_device = daq_device.get_ai_device()
    ai_info = ai_device.get_info()
    print('\nNumber of analog input channels: {}'.format(ai_info.get_num_chans()))    
    channel = int(input('\nSelect analog input channel: '))
    data = ai_device.a_in(channel, ul.AiInputMode.SINGLE_ENDED,
                          ul.Range.BIP10VOLTS, ul.AInFlag.DEFAULT)
    print('\nChannel', channel, 'Data:', data)

    # Get AoDevice and AoInfo objects for the analog output subsystem
    ao_device = daq_device.get_ao_device()
    ao_info = ao_device.get_info()
    print('\nNumber of analog output channels: {}'.format(ao_info.get_num_chans()))    
    channel = int(input('\nSelect analog output channel: '))
    value = float(input('\nOutput value: '))
    data = ao_device.a_out(channel, analog_range=ul.Range.BIP10VOLTS, flags=[ul.AOutFlag.DEFAULT], data=value)
    print('\nChannel', channel, 'was set to:', data)

    # Get AiDevice and AiInfo objects for the analog input subsystem
    dio_device = daq_device.get_dio_device()
    dio_info = dio_device.get_info()
    print('\nNumber of digital input/output channels: {}'.format(ai_info.get_num_chans()))    
    channel = int(input('\nSelect digital input channel: '))
    data = dio_device.d_in(channel, ul.AiInputMode.SINGLE_ENDED,
                          ul.Range.BIP10VOLTS, ul.AInFlag.DEFAULT)
    print('\nChannel', channel, 'Data:', data)

    # Read and display voltage values for all analog input channels
    # for channel in range(ai_info.get_num_chans()):
    #    data = ai_device.a_in(channel, AiInputMode.SINGLE_ENDED,
    #                          Range.BIP10VOLTS, AInFlag.DEFAULT)
    #    print('Channel', channel, 'Data:', data)

    daq_device.disconnect()
    # print('disconnected' if !daq_device.is_connected())
    daq_device.release()

except ul.ULException as e:
    print('\n', e)  # Display any error messages
