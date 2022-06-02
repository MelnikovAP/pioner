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
    calibration = Calibration()
    calibration.read('./settings/calibration.json')
    # calibration.read('./settings/default_calibration.json')
    
    # TODO: read from somewhere
    time_temp_table = {
        PhysQuantity.TIME: [0, 100, 1000, 1500, 2000, 3000],
        PhysQuantity.TEMPERATURE: [0, 0, 300, 300, 0, 0],
        # PhysQuantity.TEMPERATURE: [0, 0, 5, 5, 0, 0],
    }

    with FastHeat(time_temp_table, calibration) as fh:
        voltage_profiles = fh.arm()

    # for debug, remove later
        import matplotlib.pyplot as plt
        fig, ax1 = plt.subplots()
        ax1.plot(voltage_profiles['ch0'])
        ax1.plot(voltage_profiles['ch1'])
        plt.show()
    # ----------------------------------------
        fh.run()
        fh_data = fh.get_ai_data()

    # for debug, remove later
        import matplotlib.pyplot as plt
        fh_data.plot()
        plt.show()
    # ----------------------------------------


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        print(e)
