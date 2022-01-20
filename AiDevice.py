from uldaq import AiInputMode, ScanOption, create_float_buffer, AInFlag
from sys import stdout
from os import system
import numpy as np
from matplotlib import pyplot as plt

def Ai_connect(daq_device):
    return(daq_device.get_ai_device())

def Ai_get_info(ai_device):
    ai_info = ai_device.get_info()
    return({'Channels number':ai_info.get_num_chans(),
        })

def Ai_cont_scan(ai_device, channel:int, sample_rate:int):

    input_mode = AiInputMode.SINGLE_ENDED 
    scan_options = ScanOption.CONTINUOUS
    ranges = ai_device.get_info().get_ranges(input_mode)

    sample_data = create_float_buffer(1, sample_rate)

    # starting aquisition
    rate = ai_device.a_in_scan(channel, channel, input_mode,
                                ranges[0],sample_rate,
                                sample_rate, scan_options, AInFlag.DEFAULT, 
                                sample_data)
    data = np.array([])
    read_lower = True
    half_buff_size = int(sample_rate/2)
    try:
        while True:
            try:
                status, transfer_status = ai_device.get_scan_status()
                index = transfer_status.current_index
                #stdout.write('\033[1;1H')
                #stdout.write('\x1b[2K')
                #print(index)
                if index>=half_buff_size and read_lower:
                    data = np.append(data, np.array(sample_data[:half_buff_size]))
                    read_lower = False
                elif index<half_buff_size and not read_lower:
                    data = np.append(data, np.array(sample_data[half_buff_size:]))
                    read_lower = True
            except (ValueError, NameError, SyntaxError):
                break
    except KeyboardInterrupt:
        ai_device.scan_stop()
        #system('clear')
        print(len(data))
        #plt.plot(data)
        #plt.show()

def Ai_fast_scan(ai_device, channel:int, sample_rate:int):
    pass
    
