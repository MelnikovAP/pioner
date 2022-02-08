from mccdaq import *
import uldaq as ul
import time as ti
import numpy as np

class AnalogInput(MCCDAQ):

#______________________________________________________________________
# Construction
#______________________________________________________________________
	def __init__(self, sampling_rate = 1e1, recording_duration = 1.,
				low_channel = 0, high_channel = 0 \
				, scan_frq = 1e3 \
				, *args, **kwargs \
				):

		self.sampling_rate = sampling_rate
		self.recording_duration = recording_duration
		self.scan_frq = scan_frq
		self.low_channel = low_channel
		self.high_channel = high_channel

		super(AnalogInput, self).__init__(*args, **kwargs)
		self.PrepareAnalogAcquisition()

		self.alive = True

	def PrepareAnalogAcquisition(self):
		try:
			samples_per_channel = int(self.recording_duration*self.sampling_rate)
			# The default input mode is SINGLE_ENDED.
			input_mode = ul.AiInputMode.SINGLE_ENDED
			# If SINGLE_ENDED input mode is not supported, set to DIFFERENTIAL.
			if self.ai_info.get_num_chans_by_mode(ul.AiInputMode.SINGLE_ENDED) <= 0:
				input_mode = ul.AiInputMode.DIFFERENTIAL

			flags = ul.AInScanFlag.DEFAULT

			# Get the number of channels and validate the high channel number.
			number_of_channels = self.ai_info.get_num_chans_by_mode(input_mode)
			if self.high_channel >= number_of_channels:
				self.high_channel = number_of_channels - 1
			channel_count = self.high_channel - self.low_channel + 1

			# Get a list of supported ranges and validate the range index.
			ranges = self.ai_info.get_ranges(input_mode)
			if self.range_index >= len(ranges):
				self.range_index = len(ranges) - 1

			# Allocate a buffer to receive the data.
			self.buffer = ul.create_float_buffer(channel_count, samples_per_channel)

			recording_mode = self.recording_mode

			# store settings (keywords for self.analog_input.a_in_scan)
			self.recording_settings = dict(
									low_channel = self.low_channel,
									high_channel = self.high_channel,
									input_mode = input_mode,
									analog_range = ranges[self.range_index],
									samples_per_channel = samples_per_channel,
									rate = self.sampling_rate,
									options = recording_mode,
									flags = flags,
									data = self.buffer,
									)
		except Exception as e:
			print('\n', e)


	def Record(self):
		self.times['start'] = ti.time()
		self.rate = self.analog_input.a_in_scan(**self.recording_settings)
		while True:
			ti.sleep(1/self.scan_frq)
			if self.DAQIsIdle():
				self.times['stop'] = ti.time()
				break
		print('recording lasted for {:.3f} s'.format(self.times['stop'] - self.times['start']))

	def RetrieveOutput(self):
		# take data from the buffer
		data = np.array(self.buffer)
		return data
