import numpy as np
from typing import Union, List, Dict
from pymodaq.control_modules.move_utility_classes import (DAQ_Move_base, comon_parameters_fun,
                                                          main, DataActuatorType, DataActuator)

from pymodaq_utils.utils import ThreadCommand  # object used to send info back to the main thread
from pymodaq_gui.parameter import Parameter

from pymodaq_plugins_eurotherm.hardware.Eurotherm_EPC3008 import EurothermEPC3008, get_epc3008

class DAQ_Move_EPC3008(DAQ_Move_base):
    """ Instrument plugin class for an actuator.
    
    This object inherits all functionalities to communicate with PyMoDAQ’s DAQ_Move module through inheritance via
    DAQ_Move_base. It makes a bridge between the DAQ_Move module and the Python wrapper of a particular instrument.

    TODO Complete the docstring of your plugin with:
        * The set of controllers and actuators that should be compatible with this instrument plugin.
        * With which instrument and controller it has been tested.
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
    is_multiaxes = False
    _axis_names: Union[List[str], Dict[str, int]] = ['Temperature']
    _controller_units: Union[str, List[str]] = '°C'
    _epsilon: Union[float, List[float]] = 0.1
    data_actuator_type = DataActuatorType.float

    params = [
        {'title': 'IP address', 'name': 'ip_address', 'type': 'str', 'value': '134.212.36.218'},
        {'title': 'Ramp params ', 'name': 'ramp_param', 'type': 'group', 'children': [
            {'title': 'Speed (°C/min)', 'name': 'ramp_speed', 'type': 'int', 'value': 20},
            {'title': 'Speed verif', 'name': 'ramp_verif', 'type': 'str', 'value': '', 'readonly': True},
            {'title': 'Ramp unit', 'name': 'ramp_unit', 'type': 'str', 'value': '', 'readonly': True}
            ]},
         {'title': 'Temp limits', 'name': 'limits', 'type': 'group', 'children': [
             {'title': 'High', 'name': 'high_limit', 'type': 'int'},
             {'title': 'Low', 'name': 'low_limit', 'type': 'int'},
             {'title': 'Limits verif', 'name': 'limits_verif', 'type': 'str', 'value': '', 'readonly': True},
         ]},
                ] + comon_parameters_fun(is_multiaxes, axis_names=_axis_names, epsilon=0.1)

    def ini_attributes(self):
        self.controller: EurothermEPC3008 = None
        self.ip = self.settings.child('ip_address').value()
        self.ramp_speed = self.settings.child('ramp_param', 'ramp_speed').value()

    def get_actuator_value(self) -> DataActuator:
        """Get the current value from the hardware with scaling conversion.
        Returns
        -------
        float: The position obtained after scaling conversion.
        """
        pos = DataActuator(data=[np.array([self.controller.get_pv()])],
                           units=self.axis_unit)
        # pos = DataActuator(data=self.controller.get_pv(), units=self.axis_unit)
        pos = self.get_position_with_scaling(pos)
        return pos

    def close(self):
        if self.is_master:
            self.controller.protocol.close_connection()

    def set_ramp(self):
        self.ramp_speed = self.settings.child('ramp_param', 'ramp_speed').value()
        self.controller.set_sp_rate_up(self.ramp_speed)
        self.controller.set_sp_rate_down(self.ramp_speed)
        self.settings.child('ramp_param', 'ramp_verif').setValue(
            f"{self.controller.get_sp_rate_up()} / {self.controller.get_sp_rate_down()}")

    def commit_settings(self, param: Parameter):
        if param.name() == 'ip_address':
            self.controller.protocol.close_connection()
            self.ip = self.settings.child('ip_address').value()
        elif param.name() == 'ramp_speed':
            self.set_ramp()
        elif param.name() == 'high_limit':
            self.controller.set_sp_high_limit(self.settings.child('limits', 'high_limit').value())
            self.settings.child('limits', 'limits_verif').setValue(
                f"{self.controller.get_sp_low_limit()} / {self.controller.get_sp_high_limit()} ")
        elif param.name() == 'low_limit':
            self.controller.set_sp_low_limit(self.settings.child('limits', 'low_limit').value())
            self.settings.child('limits', 'limits_verif').setValue(
                f"{self.controller.get_sp_low_limit()} / {self.controller.get_sp_high_limit()} ")

    def ini_stage(self, controller=None):
        if self.is_master:
            self.controller = get_epc3008(self.ip)

            self.settings.child('ramp_param', 'ramp_unit').setValue(str(self.controller.get_sp_rate_units()))
            self.settings.child('limits', 'limits_verif').setValue(
                f"{self.controller.get_sp_low_limit()} / {self.controller.get_sp_high_limit()} ")

            self.set_ramp()

            current_value = self.get_actuator_value()
            self.move_abs(current_value)
            self.emit_status(ThreadCommand('move_done', [current_value]))
            initialized = True if self.controller is not None else False
        else:
            self.controller = controller
            initialized = True

        info = f"EPC3008 {self.ip} connected"
        return info, initialized

    def move_abs(self, value: DataActuator):
        """ Move the actuator to the absolute target defined by value
        Parameters
        ----------
        value: (float) value of the absolute target positioning
        """
        value = self.check_bound(value)  #if user checked bounds, the defined bounds are applied here
        self.target_value = value
        self.controller.set_target_sp(self.target_value)
        self.emit_status(ThreadCommand('Update_Status', [f'Setpoint {value}°C']))

    def move_rel(self, value: DataActuator):
        value = self.check_bound(self.current_value + value) - self.current_value
        self.target_value = value + self.current_value
        self.controller.set_target_sp(self.target_value)
        self.emit_status(ThreadCommand('Update_Status', [f'Setpoint {value}°C']))

    def move_home(self):
        """Call the reference method of the controller"""
        present_temp = self.get_actuator_value()
        self.move_abs(present_temp)

    def stop_motion(self):
        """Stop the actuator and emits move_done signal"""
        present_sp=self.controller.get_working_sp()
        self.move_abs(present_sp)

if __name__ == '__main__':
    main(__file__)
