import atexit as EXIT # commands to shut down processes
import sys as SYS

import uldaq as UL

class MCCDAQ():
	# analog input recording mode
	recording_mode = UL.ScanOption.BLOCKIO
	# recording_mode = UL.ScanOption.CONTINUOUS

	alive = False # alive only when ai\ao devices start

#______________________________________________________________________
# constructor
#______________________________________________________________________

	def __init__(self, device_nr=0):
		self.daq_device = None
		self.times = {}
		self.range_index = 0
		self.AssembleAndConnect(descriptor_index = device_nr)
		self.label = str(self)
		EXIT.register(self.Quit)

	def AssembleAndConnect(self, descriptor_index = 0):
		# connect to the DAQ device
		try:
			interface_type = UL.InterfaceType.USB
			# Get descriptors for all of the available DAQ devices.
			devices = UL.get_daq_device_inventory(interface_type)
			number_of_devices = len(devices)
			if number_of_devices == 0:
				raise Exception('Error: No DAQ devices found')
			self.daq_device = UL.DaqDevice(devices[descriptor_index])

		### digital input
			port_types_index = 0
			# Get the DioDevice object and verify that it is valid.
			self.digital_io = self.daq_device.get_dio_device()
			if self.digital_io is None:
				raise Exception('Error: The DAQ device does not support digital input')
			#Get the port types for the device(AUXPORT, FIRSTPORTA, ...)
			dio_info = self.digital_io.get_info()
			port_types = dio_info.get_port_types()
			if port_types_index >= len(port_types):
				port_types_index = len(port_types) - 1
			self.port = port_types[port_types_index]

		### analog input
			# Get the AiDevice object and verify that it is valid.
			self.analog_input = self.daq_device.get_ai_device()
			if self.analog_input is None:
				raise Exception('Error: The DAQ device does not support analog input')
			# Verify that the specified device supports hardware pacing for analog input.
			self.ai_info = self.analog_input.get_info()
			if not self.ai_info.has_pacer():
				raise Exception('\nError: The specified DAQ device does not support hardware paced analog input')

		### connect
			# Establish a connection to the DAQ device.
			self.daq_device.connect()

		except Exception as e:
			print('constructor fail\n', e)

		print('\nConnected to', str(self))









# for digital I/O
	def SetPins(self):
		# implemented by sub class
		raise TypeError('Digital pin setup not implemented!')
		pass








#______________________________________________________________________
# DAQ status
#______________________________________________________________________
	def GetDAQStatus(self):
		return self.analog_input.get_scan_status()

	def DAQIsRunning(self):
		return self.analog_input.get_scan_status()[0] is UL.ScanStatus.RUNNING

	def DAQIsIdle(self):
		return self.analog_input.get_scan_status()[0] is UL.ScanStatus.IDLE

#______________________________________________________________________
# I/O
#______________________________________________________________________


	def __str__(self):
		descriptor = self.daq_device.get_descriptor()
		return descriptor.dev_string

	def __enter__(self):
		# required for context management ("with")
		return self
		
	def __exit__(self, exc_type, exc_value, traceback):
		# exiting when in context manager
		if not self.alive:
			return
		self.Quit()

	def Quit(self):
		# safely exit
		if not self.alive:
			SYS.exit()
			return

		if self.daq_device:
			# Stop the acquisition if it is still running.
			if not self.DAQIsIdle():
				self.analog_input.scan_stop()
			if self.daq_device.is_connected():
				self.daq_device.disconnect()
			self.daq_device.release()
		print('safely exited')
		self.alive = False

		SYS.exit()
