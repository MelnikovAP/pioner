from acquisition_manager import AcquisitionManager
from settings_parser import SettingsParser
from argparse import ArgumentParser


# provide with-as for Settings classes
# make abstract classes "Params", "AnalogParams" and "Device"?
# think about name "self.samples_per_channel"
# think about possible changing of "self._params.input_mode"
# make singletons?
# provide output_folder
# provide commentaries for each class


def parse_args():
    parser = ArgumentParser(description='.')
    parser.add_argument('--path_to_settings', type=str, help='Path to the configuration file.')
    # parser.add_argument('--output_folder', type=str, help='Path to the output folder for resulting files and logs.')
    # parser.add_argument('--do_clear_output', type=bool, default=True, action=BooleanOptionalAction,
    #                     help='True if all existing files should be removed from the output directory.')
    return parser.parse_args()


def main():
    args = parse_args()
    parser = SettingsParser(args.path_to_settings)

    with AcquisitionManager(parser.get_scan_params(),
                            parser.get_daq_params(),
                            parser.get_ai_params(),
                            parser.get_ao_params()) as am:
        am.run()


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        print(e)
