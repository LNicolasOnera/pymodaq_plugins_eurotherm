import numpy as np

from pymodaq_utils.utils import ThreadCommand
from pymodaq_data.data import DataToExport
from pymodaq_gui.parameter import Parameter

from pymodaq.control_modules.viewer_utility_classes import DAQ_Viewer_base, comon_parameters, main
from pymodaq.utils.data import DataFromPlugins

from pymodaq_plugins_eurotherm.hardware.Eurotherm_EPC3008 import EurothermEPC3008


class DAQ_0DViewer_EPC3008(DAQ_Viewer_base):
    """ Instrument plugin class for a OD viewer.
    
    This object inherits all functionalities to communicate with PyMoDAQ’s DAQ_Viewer module through inheritance via
    DAQ_Viewer_base. It makes a bridge between the DAQ_Viewer module and the Python wrapper of a particular instrument.

    TODO Complete the docstring of your plugin with:
        * The set of instruments that should be compatible with this instrument plugin.
        * With which instrument it has actually been tested.
        * The version of PyMoDAQ during the test.
        * The version of the operating system.
        * Installation instructions: what manufacturer’s drivers should be installed to make it run?

    Attributes:
    -----------
    controller: object
        The particular object that allow the communication with the hardware, in general a python wrapper around the
         hardware library.
         
    # TODO add your particular attributes here if any

    """
    params = comon_parameters+[
        {'title': 'IP address', 'name': 'ip_address', 'type': 'str', 'value': '134.212.36.218'},
        {'title': 'Units', 'name': 'units', 'type': 'group', 'children': [
            {'title': 'Temperature', 'name': 'temp', 'type': 'str', 'value': '', 'readonly': True},
            {'title': 'Ramp speed', 'name': 'ramp_speed', 'type': 'str', 'value': '', 'readonly': True}
        ]},
        ]

    def ini_attributes(self):
        self.controller: EurothermEPC3008 = None
        self.ip = self.settings.child('ip_address').value()

    def commit_settings(self, param: Parameter):
        """Apply the consequences of a change of value in the detector settings

        Parameters
        ----------
        param: Parameter
            A given parameter (within detector_settings) whose value has been changed by the user
        """
        if param.name() == "ip_address":
            self.controller.protocol.close_connection()
            self.ip=self.settings.child('ip_address').value()


    def ini_detector(self, controller=None):
        """Detector communication initialization"""
        if self.is_master:
            self.controller = EurothermEPC3008(self.ip)

            initialized = True
        else:
            self.controller = controller
            initialized = True

        self.settings.child('units', 'temp').setValue(str(self.controller.get_temp_units()))
        self.settings.child('units', 'ramp_speed').setValue(str(self.controller.get_sp_rate_units()))

        self.dte_signal_temp.emit(DataToExport(name='EPC3008',
                                               data=[DataFromPlugins(name='Temp (°C)',
                                                                    data=[np.array([0])],
                                                                    dim='Data0D',
                                                                    labels=['Temp (°C)'])]))

        print(f"Connected to {self.ip}")
        info = f"EPC3008 {self.ip} connected"
        return info, initialized

    def close(self):
        """Terminate the communication protocol"""
        self.controller.protocol.close_connection()

    def grab_data(self, Naverage=1, **kwargs):
        """Start a grab from the detector"""

        data = np.array([self.controller.get_pv()])
        self.dte_signal.emit(DataToExport(name='EPC3008',
                                          data=[DataFromPlugins(name='Temp (°C)', data=data,
                                                                dim='Data0D', labels=['Temp (°C)'])]))



    def stop(self):
        """Stop the current grab hardware wise if necessary"""
        return ''


if __name__ == '__main__':
    main(__file__)
