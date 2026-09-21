# -*- coding: utf-8 -*-
"""
Created on Tue Jun 24 16:31:17 2025

@author: bpons
"""
from pymodbus.client import ModbusTcpClient   # pip install pymodbus
import nest_asyncio
nest_asyncio.apply()
import numpy as np
import asyncio
import time

# This first class aims to implement the protocol used by EPC3008 devices (Modbus TCP).
class ModbusTCP :
    """Class of all the methods to communicate with an EPC 3008 device from creating the command
    to sending it and reading its response."""
    
    def __init__(self, ip : str):
        self.client = None
        self.open_connection(ip)

    def open_connection(self, ip : str) -> None:
        """Opens the connection with the EPC 3008 device."""
        try:
            self.client = ModbusTcpClient(ip, timeout=1)
            self.client.connect()
        except Exception as e:
            print(f"Failed to connect to {ip}: {e}")
            self.client = None  

    def close_connection(self) -> None:
        """Closes the connection with the EPC 3008 device."""
        if self.client:
            try:
                self.client.close()
            except Exception as e:
                print(f"Closing failure: {e}")

    def read_holding_register(self, address: int, count: int = 1) -> list | None:
        """Reads holding register(s) from the device. Returns None if failed."""
        if not self.client:
            return None
        try:
            resp = self.client.read_holding_registers(address, count=count)
            if resp:
                if resp.isError():
                    return None
                return resp.registers
            else:
                return None
        except Exception:
            return None

    def write_register(self, address : int, value : list[int]) -> None:
        """Connects to the EPC 3008 device and writes the register(s) at the given address."""
        try :
            resp = self.client.write_registers(address, value)
            if resp:
                if resp.isError():
                    raise ConnectionError(f"Pymodbus returns an error : {resp}.")
        except Exception:
            return False

    @staticmethod
    def decode_resp_to_string(resp : list[int]) -> str:
        """Decodes the response read from the registers to a string."""
        string = ''
        for number in resp:
            binary_number = bin(number)
            if (binary_number[2:-8] != '') & (binary_number[-8:] != ''):
                two_letters = chr(int(binary_number[2:-8], 2)) + chr(int(binary_number[-8:], 2))
                string += two_letters
            else :
                string += ' '
        return string

    def encode_number(self, number: float, resolution_factor: int, power: int = 16) -> int:
        """Returns the encoded representation of the entered signed number."""
        repr_int = int(number * resolution_factor)
        if repr_int < 0:
            repr_int = 2**power + repr_int
        if (0 > repr_int) or (repr_int > 2**power):
            raise ValueError(f"The number '{number}' is represented by {repr_int}, which is not between 0 and {2**power}.")
        return repr_int
    
    def decode_number(self, number: int, resolution_factor: int, power: int = 16) -> float:
        """Returns the signed number according to its representation."""
        if number > 2**(power - 1):
            number = number - 2**power
        return round(number * (1 / resolution_factor), 4)

    @staticmethod
    def get_ending_time(duration : str) -> str:
        """Returns the ending time in HH:MM:SS format."""
        current_time = time.strftime("%H:%M:%S", time.localtime())
        current_hour = int(current_time[:2]) + int(duration[:2])
        current_minute = int(current_time[3:5]) + int(duration[3:5])
        current_second = int(current_time[6:]) + int(duration[6:])
        time_list = [current_second, current_minute, current_hour]
        for i in range(0, 2):
            if time_list[i] >= 60 :
                time_list[i+1] += time_list[i]//60
            time_list[i] = time_list[i]%60
            if time_list[i]<10:
                time_list[i] = '0' + str(time_list[i])
            else : 
                time_list[i] = str(time_list[i])
        if time_list[2] >= 24:
            time_list[2] = time_list[2]%60
            # Note : if the experiment is more than a day long, add conditions for the date.
        if time_list[2] < 10:
            time_list[2] = '0' + str(time_list[2])
        else : 
            time_list[2] = str(time_list[2])
        return time_list[2] + ':' + time_list[1] + ':' + time_list[0]
        
    
class EurothermEPC3008:
    """Class for communicating with an EPC3008 instrument through Ethernet.
    It contains the methods I thought were essential as well as more complex ones aiming to
    facilitate the user's final experience."""
    
    def __init__(self, ip : str = None):
        self.resolution_factor = None
        self.list_of_init_values = None
        if not ip :
            self.ip = input("Enter IP address (example: 134.212.36.218): ")
        else :
            self.ip = ip
        self.protocol = ModbusTCP(self.ip)
    
    def initialize_regulator(self, target_value: float = None, sp_high_limit: float = None, sp_low_limit: float = None) -> bool:
        """Initializes the regulator with specified values and returns True if successful."""
        if not self.protocol.client:
            return False
    
        # Récupère la résolution, avec une valeur par défaut si échec
        resolution = self.get_resolution()
        if resolution is None:
            self.resolution_factor = 1  # Valeur par défaut
        else:
            self.resolution_factor = resolution
    
        # Initialise les valeurs
        self.list_of_init_values = [time.strftime("%Y-%m-%d", time.localtime()), time.strftime("%H:%M:%S", time.localtime())]
        self.force_standby()
        self.list_of_init_values.append(self.get_temp_units())
        self.list_of_init_values.append(self.get_sp_rate_units())
        print(f"Regulator's units are : {self.list_of_init_values[2]} for set point and {self.list_of_init_values[3]} for ramp's speed.")
        self.list_of_init_values.append(self.get_pv_status())
    
        if target_value is not None:
            self.set_target_sp(target_value)
        self.list_of_init_values.append(self.get_target_sp())
    
        if sp_high_limit is not None:
            self.set_sp_high_limit(sp_high_limit)
        self.list_of_init_values.append(self.get_sp_high_limit())
    
        if sp_low_limit is not None:
            self.set_sp_low_limit(sp_low_limit)
        self.list_of_init_values.append(self.get_sp_low_limit())
    
        self.stop_standby()
        self.set_automatic_mode()
    
        return True

    # The following methods read or write values to EPC3008 devices.
    # Addresses may change between units, verify them in Eurotherm iTools software.
    # Since I extracted the methods I found useful, do not hesitate to add the ones you need.
    
    # Instrument tab on iTools
    adr_temp_units = 516
    adr_firmware_version = 18432
    adr_force_standby = 1085
    adr_execution_status = 1088
    
    # AI tab
    adr_resolution = 1922
    adr_pv = 289
    adr_pv_status = 1932
    
    # CT tab
    adr_leak_current = 1591
    
    # LOOP tab
    adr_mode_auto_manual = 273
    adr_target_sp = 2
    adr_integral_hold = 264
    adr_sp_high_limit = 111
    adr_sp_low_limit = 112
    adr_sp_rate_units = 531
    # Note : for the values units, check get_temp_units() and get_sp_rate_units() methods.
    adr_sp_rate_up = 35
    adr_sp_rate_down = 1667
    adr_sp_rate_done = 1673
    
    def get_temp_units(self) -> str:
        """Returns temperature units"""
        resp = self.protocol.read_holding_register(self.adr_temp_units)
        list_values = ["°C", "°F", "K"]
        if not (0<= resp[0] < len(list_values))&(type(resp[0]) == int):
            raise ValueError(f"Error in get_temp_units value : {resp} not expected.")
        return list_values[resp[0]]

    def get_firmware_version(self) -> str:
        """Returns firmware version."""
        # This method (not very useful I reckon) is meant to give an example of how to decode string values from the
        # regulator, if a more useful application is needed.
        resp = self.protocol.read_holding_register(self.adr_firmware_version, 3)
        return self.protocol.decode_resp_to_string(resp, self.resolution_factor)
        
    def force_standby(self) -> None:
        """Forces standby mode."""
        self.protocol.write_register(self.adr_force_standby, [1])
    
    def stop_standby(self) -> None:
        """Stops standby mode."""
        self.protocol.write_register(self.adr_force_standby, [0])
        
    def get_standby_status(self) -> str:
        """Returns regulator status (standby or not)."""
        resp = self.protocol.read_holding_register(self.adr_execution_status)
        list_values = ["Working", "Standby", "Startup"]
        if not (0<= resp[0] < len(list_values))&(type(resp[0]) == int):
            raise ValueError(f"Error in get_standby_status value : {resp} not expected.")
        return list_values[resp[0]]

    def get_resolution(self) -> int:
        """Returns the resolution of the device."""
        resp = self.protocol.read_holding_register(self.adr_resolution)
        if resp is None or len(resp) == 0:
            return None
        list_values = [1, 10, 100, 1000, 10000]
        if not (0 <= resp[0] < len(list_values)) or not isinstance(resp[0], int):
            return None
        return list_values[resp[0]]

    def get_pv(self) -> float:
        """Returns regulator's TC measured value."""
        resp = self.protocol.read_holding_register(self.adr_pv)
        return self.protocol.decode_number(resp[0], self.resolution_factor)
    
    def get_pv_status(self) -> str:
        """Returns TC status."""
        resp = self.protocol.read_holding_register(self.adr_pv_status)
        list_values = ["Good", "Not conf", "Out of range", "< range", "Hardware invalid status",
                       "Scaling", "Out", "Bad"]
        if not (0<= resp[0] < len(list_values))&(type(resp[0]) == int):
            raise ValueError(f"Error in get_pv_status value : {resp} not expected.")
        return list_values[resp[0]]
        
    def get_leak_current(self) -> float:
        """Returns leak current measured on IO1."""
        resp = self.protocol.read_holding_register(self.adr_leak_current)
        return self.protocol.decode_number(resp[0], self.resolution_factor)
    
    def get_mode(self) -> str:
        """Returns current regulator's mode (manual/automatic)."""
        resp = self.protocol.read_holding_register(self.adr_mode_auto_manual)
        list_values = ["Automatic mode", "Manual mode"]
        if not (0<= resp[0] < len(list_values))&(type(resp[0]) == int):
            raise ValueError(f"Error in get_mode value : {resp} not expected.")
        return list_values[resp[0]]
    
    # Note : To change mode, make sure the regulator is not in standby.
    def set_automatic_mode(self) -> None:
        """Sets the regulator to automatic mode."""
        self.protocol.write_register(self.adr_mode_auto_manual, [0])
    
    def set_manual_mode(self) -> None:
        """Sets the regulator to manual mode."""
        self.protocol.write_register(self.adr_mode_auto_manual, [1])
        
    def get_target_sp(self) -> float:
        """Returns target set point value."""
        resp = self.protocol.read_holding_register(self.adr_target_sp)
        return self.protocol.decode_number(resp[0], self.resolution_factor)
    
    def set_target_sp(self, value: float) -> None:
        """Sets the target set point value."""
        sp_value = self.protocol.encode_number(value, self.resolution_factor)
        self.protocol.write_register(self.adr_target_sp, [sp_value])
    
    def get_integral_hold_status(self) -> str:
        """Returns integral hold status."""
        resp = self.protocol.read_holding_register(self.adr_integral_hold)
        list_values = ["Integral action active", "Integral action stopped"]
        if not (0<= resp[0] < len(list_values))&(type(resp[0]) == int):
            raise ValueError(f"Error in get_integral_hold_status value : {resp} not expected.")
        return list_values[resp[0]]
    
    def activate_integral_action(self) -> None:
        """Activates the integral hold action."""
        self.protocol.write_register(self.adr_integral_hold, [0])
    
    def stop_integral_action(self) -> None:
        """Stops the integral hold action."""
        self.protocol.write_register(self.adr_integral_hold, [1])
    
    def get_sp_high_limit(self) -> float:
        """Returns the high limit for the set point."""
        resp = self.protocol.read_holding_register(self.adr_sp_high_limit)
        return self.protocol.decode_number(resp[0], self.resolution_factor)
    
    def set_sp_high_limit(self, value : float) -> None:
        """Sets the high limit for the set point."""
        sp_value = self.protocol.encode_number(value, self.resolution_factor)
        self.protocol.write_register(self.adr_sp_high_limit, [sp_value])
        
    def get_sp_low_limit(self) -> float:
        """Returns the low limit for the set point."""
        resp = self.protocol.read_holding_register(self.adr_sp_low_limit)
        return self.protocol.decode_number(resp[0], self.resolution_factor)
    
    def set_sp_low_limit(self, value : float) -> None:
        """Sets the low limit for the set point."""
        sp_value = self.protocol.encode_number(value, self.resolution_factor)
        self.protocol.write_register(self.adr_sp_low_limit, [sp_value])
    
    def get_sp_rate_units(self) -> str:
        """Returns ramp's temporal units."""
        resp = self.protocol.read_holding_register(self.adr_sp_rate_units)
        list_values = ["per second", "per minute", "per hour"]
        if not (0 <= resp[0] < len(list_values)) & (type(resp[0]) == int):
            raise ValueError(f"Error in get_integral_hold_status value : {resp} not expected.")
        return list_values[resp[0]]

    def get_sp_rate_up(self) -> float:
        """Returns ramp's rate up speed value."""
        resp = self.protocol.read_holding_register(self.adr_sp_rate_up)
        return self.protocol.decode_number(resp[0], self.resolution_factor)
    
    def set_sp_rate_up(self, value : float) -> None:
        """Sets ramp's rate up speed value."""
        # Note : if value = 0, there is no limit.
        if not value >= 0:
            raise ValueError(f"set_sp_rate_up's value should be positive; value entered : {value}.")
        sp_value = self.protocol.encode_number(value, self.resolution_factor)
        self.protocol.write_register(self.adr_sp_rate_up, [sp_value])
        
    def get_sp_rate_down(self) -> float:
        """Returns ramp's rate down speed value."""
        resp = self.protocol.read_holding_register(self.adr_sp_rate_down)
        return self.protocol.decode_number(resp[0], self.resolution_factor)
    
    def set_sp_rate_down(self, value : float) -> None:
        """Sets ramp's rate down speed value."""
        # Note : if value = 0, there is no limit.
        if not value >= 0:
            raise ValueError(f"set_sp_rate_down's value should be positive; value entered : {value}.")
        sp_value = self.protocol.encode_number(value, self.resolution_factor)
        self.protocol.write_register(self.adr_sp_rate_down, [sp_value])
    
    def get_sp_rate_done(self) -> str:
        """Returns ramp's status (done or not)."""
        resp = self.protocol.read_holding_register(self.adr_sp_rate_done)
        list_values = ["Ramping", "Ramp done"]
        if not (0 <= resp[0] < len(list_values)) & (type(resp[0]) == int):
            raise ValueError(f"Error in get_integral_hold_status value : {resp} not expected.")
        return list_values[resp[0]]
    
    
    # The following methods use the above ones to create more complex applications.
    # Do not hesitate to modify them as needed !
    
    def create_ramp(self, target_value : float, rate_up : float, rate_down : float) -> list:
        """Creates a ramp with specified conditions.
        ===========================================
        target_value: the target value for the ramp.
        rate_up: the ramp up speed value.
        rate_down: the ramp down speed value."""
        self.set_sp_rate_up(rate_up)
        self.set_sp_rate_down(rate_down)
        set_values = [time.strftime("%Y-%m-%d", time.localtime()), time.strftime("%H:%M:%S", time.localtime())]
        self.set_target_sp(target_value)
#        print(f"Ramp's status : {self.get_sp_rate_done()}.")
        set_values.append(self.get_target_sp())
        set_values.append(self.get_sp_rate_up())
        set_values.append(self.get_sp_rate_down())
        return set_values
    
    def useful_data(self) -> list:
        """Returns a list of useful regulator's data."""
        # The following commands define the data grabbed in a loop from the regulator.
        return [time.strftime("%Y-%m-%d", time.localtime()),
                                      time.strftime("%H:%M:%S", time.localtime()), self.get_pv(),
                                      self.get_target_sp(), self.get_sp_rate_done()]

    async def automatic_data_grab_iterations(self, loop_number : int = 25, sleeping_time = 1) -> list[np.ndarray]:
        """Makes loop_number data grab waiting sleeping_time between each then returns data.
        ================================
        loop_number : int (default = 25, number of data grab)
        sleeping_time : int (default = 1, waiting time in seconds between two consecutive data grabs)"""
        list_of_grabbed_data = []
        for _ in range(0, loop_number):
            list_of_grabbed_data.append(self.useful_data())
            await asyncio.sleep(sleeping_time)
        return np.array(list_of_grabbed_data)
    
    async def automatic_data_grab_duration(self, sleeping_time : int = 1, duration : str = '00:00:30') -> np.ndarray:
        """Returns an array of data grabbed every sleeping_time during duration in HH:MM:SS format.
        =================================
        sleeping_time : int (default = 1, waiting time in seconds between two consecutive data grabs)
        duration : str (default = '00:00:30', duration of the loop in HH:MM:SS format)"""
        list_of_grabbed_data = []
        ending_time = self.protocol.get_ending_time(duration)
        print(f"automatic_data_grab_duration ends at : {ending_time}")
        while ending_time > time.strftime("%H:%M:%S", time.localtime()):
            list_of_grabbed_data.append(self.useful_data())
            await asyncio.sleep(sleeping_time)
        return np.array(list_of_grabbed_data)
    
    async def automatic_data_grab_temperature_value(self, target_temp : float, sleeping_time : int = 1,
                                                    limit_duration : str = '00:00:00') -> np.ndarray:
        """Returns an array of data grabbed every sleeping_time while TC temperature is different from target_temp.
        ===================================
        target_temp : float (target temperature to stop grabbing data)
        sleeping_time : int (default = 1, waiting time in seconds between two consecutive data grabs)
        limit_duration : str (default = '00:00:00', maximum duration of the loop in HH:MM:SS format)"""
        list_of_grabbed_data = []
        ending_time = self.protocol.get_ending_time(limit_duration)
        temp_value = self.get_pv()
        if temp_value < target_temp :
            while (ending_time > time.strftime("%H:%M:%S", time.localtime()))&(temp_value < target_temp):
                list_of_grabbed_data.append(self.useful_data())
                await asyncio.sleep(sleeping_time)
                temp_value = self.get_pv()
        elif temp_value > target_temp :
            while (ending_time > time.strftime("%H:%M:%S", time.localtime()))&(temp_value > target_temp):
                list_of_grabbed_data.append(self.useful_data())
                await asyncio.sleep(sleeping_time)
                temp_value = self.get_pv()
        else :
            while (ending_time > time.strftime("%H:%M:%S", time.localtime()))&(temp_value == target_temp):
                list_of_grabbed_data.append(self.useful_data())
                await asyncio.sleep(sleeping_time)
                temp_value = self.get_pv()
        return np.array(list_of_grabbed_data)

