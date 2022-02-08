from mccdaq import *
from analoginput import *

#class AnalogInput(MCCDAQ):

def TestDAQAnalog():
	with AnalogInput(
				sampling_rate = 1e3,
				recording_duration = 2.,
				low_channel=0,
				high_channel=1,
				scan_frq = 1e6,
				) as ai:
		ai.Record()
		data = ai.RetrieveOutput()


################################################################################
### Mission Control                                                          ###
################################################################################
if __name__ == "__main__":
	TestDAQAnalog()
