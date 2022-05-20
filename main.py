from settings import SettingsParser
from calibration import Calibration
from fastheat import FastHeat
from utils import PhysQuantity

# provide with-as for Settings classes
# make abstract classes "Params", "AnalogParams" and "Device"?
# think about name "self.samples_per_channel"
# think about possible changing of "self._params.input_mode"
# make singletons?
# provide output_folder
# provide commentaries for each class


def main():
    settings = SettingsParser('./settings.json')
    calibration = Calibration()
    #calibration.read('./calibration.json')
    calibration.read('./default_calibration.json')
    
    # TODO: read from somewhere
    time_temp_table = {
        PhysQuantity.TIME: [0, 50, 450, 550, 950, 1000],
        #PhysQuantity.TEMPERATURE: [0, 0, 300, 300, 0, 0],
        PhysQuantity.TEMPERATURE: [0, 0, 1, 1, 0, 0],
    }

    with FastHeat(time_temp_table, calibration, settings) as fh:
        voltage_profiles = fh.arm()
        
    ######### for debug, remove later
        # import matplotlib.pyplot as plt
        # fig, ax1 = plt.subplots()
        # ax1.plot(voltage_profiles['ch0'])
        # ax1.plot(voltage_profiles['ch1'])
        # plt.show()
    ###################

        fh.run(voltage_profiles)
        fh_data = fh.get_ai_data()

    ######## for debug, remove later
        import matplotlib.pyplot as plt
        fh_data.plot()
        plt.show()
    ###################

if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        print(e)
