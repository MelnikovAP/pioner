import logging
import time
import uldaq as ul

# TODO: add an abstract class for device + add a mock device for testing


class DaqParams:
    """General class to represent main DAQ parameters.
    Deafult paramteres cannot be used to initialize :obj:`uldaq.DaqDevice`,
    they need to be parsed from file or specified manually.
    
    Parameters
    ----------
        interface_type : :obj:`ul.InterfaceType`
            Description
        connection_code : :obj:`int`
            Description

    """
    def __init__(self):
        self.interface_type = ul.InterfaceType.ANY  # USB = 1; BLUETOOTH = 2; ETHERNET = 4; ANY = 7 from https://www.mccdaq.com/PDFs/Manuals/UL-Linux/python/api.html#uldaq.InterfaceType
        self.connection_code = -1

    def __str__(self):
        return str(vars(self))


class DaqDeviceHandler:
    """ Class to handle connection to DAQ device with preset parameters
    
    Args
    ------
        params : :obj:`DaqParams`
            Basic parameters to initialize connection to DAQ device.

    """
    def __init__(self, params: DaqParams):
        self._params = params
        self._init_daq_device()

    def _init_daq_device(self):
        """ Looking for connected devices only with USB interface. 
        Only one device expected to be connected. 
        If no devices connected, logs and raise an error
        """
        devices = ul.get_daq_device_inventory(self._params.interface_type, 1)
        if not devices:
            error_str = "No DAQ devices found."
            logging.error("DAQ DEVICE: ERROR. {}".format(error_str))
            raise RuntimeError(error_str)

        # by default connecting only to the first DAQBoard with index 0
        self._daq_device = ul.DaqDevice(devices[0])

    def __enter__(self):
        # self.try_connect()
        return self

    def __exit__(self, exe_type, exe_value, exe_traceback):
        self.quit()

    def get_descriptor(self) -> ul.DaqDeviceDescriptor:
        """ Provides explicit access to the descriptor of connected DAQ device. 
        
        Returns
        -------- 
            :obj:`ul.DaqDeviceDescriptor` 
        """
        return self._daq_device.get_descriptor()

    def is_connected(self) -> bool:
        """ Provides explicit access to the connection status of DAQ device.
        
        Returns: 
        ---------
            :obj:`bool` 
        """
        return self._daq_device.is_connected()

    def connect(self):
        """ Basic method to connect to DAQ device only with USB interface.
        Only one device expected to be connected. 
        Logs success/unsuccess result. 
        """
        descriptor = self.get_descriptor()
        logging.info("DAQ DEVICE: Connecting to {} - please wait...".format(descriptor.dev_string))
        self._daq_device.connect(connection_code=self._params.connection_code)
        if self._daq_device.is_connected():
            logging.info("DAQ DEVICE: DAQ device has been successfully connected.")
        else:
            logging.warning("DAQ DEVICE: WARNING. DAQ device hasn't been connected.")

    def try_connect(self, timeout: int = 60, sleep_time: int = 1):
        """ Uses basic method :obj:`connect` to connect to DAQ device 
        via USB interface using timeout. 
        No action if device is already connected. 
        Logs success/unsuccess result. 

        Args
        ------  
            timeout : :obj:`int`
                Timeout to give up connecting in seconds.  
            sleep_time : :obj:`int`
                Sleeptime between connection attempts in seconds.  

        """
        for _ in range(timeout):
            if not self.is_connected():
                self.connect()
            time.sleep(sleep_time)
            if self.is_connected():
                return
        raise TimeoutError("DAQ DEVICE: Connection timed out.")

    def disconnect(self):
        """ Basic method to disconnect DAQ device. Logs result."""
        self._daq_device.disconnect()
        logging.info("DAQ DEVICE: DAQ device has been disconnected.")

    def release(self):
        """ Basic method to release DAQ device. Logs result."""
        self._daq_device.release()
        logging.info("DAQ DEVICE: DAQ device has been released.")

    def reset(self):
        """ Basic method to reset DAQ device. Logs result."""
        self._daq_device.reset()
        logging.info("DAQ DEVICE: DAQ device has been reset.")

    def quit(self):
        """ Basic method to disconnect and release DAQ device. Logs result. """
        if self.is_connected():
            self.disconnect()
        self.release()
        logging.info("DAQ DEVICE: DAQ device has been disconnected and released.")

    def get(self) -> ul.DaqDevice:
        """ Provides explicit access to uldaq.daq_device.
        
        Returns
        ------- 
            :obj:`ul.DaqDevice` 
        """
        return self._daq_device

    def get_ai_device(self) -> ul.AiDevice:
        """ Provides explicit access to uldaq.ai_device.
        
        Returns
        -------
            :obj:`ul.AiDevice`
        """
        return self._daq_device.get_ai_device()

    def get_ao_device(self) -> ul.AoDevice:
        """ Provides explicit access to uldaq.ao_device.
        
        Returns
        ------- 
            :obj:`ul.AoDevice`
        """
        return self._daq_device.get_ao_device()
