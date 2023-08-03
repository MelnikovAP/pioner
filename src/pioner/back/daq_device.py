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
        interface_type : :obj:`uldaq.InterfaceType`
            USB = 1; BLUETOOTH = 2; ETHERNET = 4; ANY = 7.
            Refer to :obj:`uldaq` documentation.
            By default, :obj:`uldaq.InterfaceType.ANY` is used.
        connection_code : :obj:`int`
            The connection code becomes active after cycling power 
            to the device or calling :obj:`uldaq.DaqDevice.reset()`. 
            This function only applies to DAQ Ethernet devices.
            By default -1 used. 

    """
    def __init__(self):
        self.interface_type = ul.InterfaceType.ANY
        self.connection_code = -1

    def __str__(self):
        return str(vars(self))


class DaqDeviceHandler:
    """ Class to handle connection to DAQ device with preset parameters.
    On initiallization, looks for connected devices only via USB interface. 
    Only one device is expected to be connected. 
    
    Parameters
    ----------
        params : :obj:`DaqParams`
            Basic parameters to initialize connection to DAQ device.
    
    Raises
    -------
        :obj:`RuntimeError`
            If no devices connected, logs and raises error

    """
    def __init__(self, params: DaqParams):
        self._params = params
        self._init_daq_device()

    def _init_daq_device(self):
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
            :obj:`class`  
                A class :obj:`uldaq.DaqDeviceDescriptor` with 
                the following properties of connected device:
                :obj:`product_name`, :obj:`product_id`, 
                :obj:`property dev_interface`, 
                :obj:`property dev_string`, 
                :obj:`property unique_id`

        """
        return self._daq_device.get_descriptor()

    def is_connected(self) -> bool:
        """ Provides explicit access to the connection status of DAQ device.
        
        Returns 
        ---------
            :obj:`bool` 
                :obj:`True` if connected, :obj:`False` if not
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
                Timeout to give up connecting in seconds. By default = 60 
            sleep_time : :obj:`int`
                Sleeptime between connection attempts in seconds. By default = 1 

        Raises
        -------
            :obj:`TimeoutError`
                If device can't be found via selected interface, 
                logs and raises error
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
        """ Provides explicit access to :obj:`uldaq.daq_device`.
        
        Returns
        ------- 
            :obj:`class` 
                :obj:`uldaq.DaqDevice` class with properties and methods, 
                provided by :obj:`uldaq` library.
        """
        return self._daq_device

    def get_ai_device(self) -> ul.AiDevice:
        """ Provides explicit access to :obj:`uldaq.ai_device`.
        
        Returns
        -------
            :obj:`class` 
                :obj:`uldaq.AiDevice` class with properties and methods, 
                provided by :obj:`uldaq` library.
        """
        return self._daq_device.get_ai_device()

    def get_ao_device(self) -> ul.AoDevice:
        """ Provides explicit access to uldaq.ao_device.
        
        Returns
        ------- 
            :obj:`class` 
                :obj:`uldaq.AoDevice` class with properties and methods, 
                provided by :obj:`uldaq` library.
        """
        return self._daq_device.get_ao_device()
