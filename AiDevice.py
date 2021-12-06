from uldaq import AiInputMode, ScanOption, create_float_buffer, AInFlag
from os import system
from time import sleep

def Ai_connect(daq_device):
    ai_device = daq_device.get_ai_device()
    ai_info = ai_device.get_info()
    return(ai_device, ai_info)

def Ai_cont_scan(ai_device, ai_info):
    print('''
        ====================================
        ======= continious scan mode =======
        ====================================
          ''')
    print('\n\tNumber of analog input channels: {}'.format(ai_info.get_num_chans()))    
    channel = int(input('\n\tSelect analog input channel: '))
    
    input_mode = AiInputMode.SINGLE_ENDED
    ranges = ai_info.get_ranges(input_mode)
    samples_per_channel = 10000
    rate = 1000
    scan_options = ScanOption.CONTINUOUS

    print('\n\tSelected channel: ', channel)
    print('\tInput mode: ', input_mode.name)
    print('\tRange: ', ranges[0].name)
    print('\tSamples per channel: ', samples_per_channel)
    print('\tRate: ', rate, 'Hz')

    data = create_float_buffer(1, samples_per_channel)
    try:
        input('\n\tHit ENTER to continue\n')
    except (NameError, SyntaxError):
        pass

    act_rate = ai_device.a_in_scan(channel, channel, input_mode,
                                   ranges[0], samples_per_channel,
                                   rate, scan_options, AInFlag.DEFAULT, data)
    try:
        while True:
            try:
                system('clear')
                status, transfer_status = ai_device.get_scan_status()
                print('Please enter CTRL + C to terminate the process\n')
                index = transfer_status.current_index
                print('current total count = ', transfer_status.current_total_count)
                print('current scan count = ', transfer_status.current_scan_count)
                print('current index = ', index, '\n')
                print('actual scan rate = ', '{:.6f}'.format(act_rate), 'Hz\n')
                print('channel {} = '.format(channel), data[index])
                sleep(0.1)
            except (ValueError, NameError, SyntaxError):
                break
    except KeyboardInterrupt:
        pass
