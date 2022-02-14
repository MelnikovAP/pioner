from argparse import ArgumentParser  #, BooleanOptionalAction
from settings_parser import SettingsParser


# provide bitwise OR for some params
# provide "while True"
# make abstract classes "Params", "AnalogParams" and "Device"?
# think about name "self.samples_per_channel"
# think about possible changing of "self._params.input_mode"
# move "amplitude" to params (ao_params or scan_params ?)
# update AcquisitionManager
# make singletones?
# provide output_folder


def parse_args():
    parser = ArgumentParser(description='.')
    parser.add_argument('--path_to_settings', type=str, help='Path to the configuration file.')
    # parser.add_argument('--output_folder', type=str, help='Path to the output folder for resulting files and logs.')
    # parser.add_argument('--do_clear_output', type=bool, default=True, action=BooleanOptionalAction,
    #                     help='True if all existing files should be removed from the output directory.')
    return parser.parse_args()


def main():
    args = parse_args()

    settings = SettingsParser(args.path_to_settings)

    with AcquisitionManager as am:
        am.run()


if __name__ == '__main__':
    try:
        main()
    except BaseException as e:
        print(e)
