from pymodbus.client import ModbusTcpClient   # pip install pymodbus
import nest_asyncio
nest_asyncio.apply()
import ipaddress
import threading

_connections: dict = {}

def get_epc3008(ip: str) -> 'EurothermEPC3008':
    """Returns the opend connection for this IP if existing or open a new one.
    This method was created to check if an EPC3008 was already opened before opening it again.
    It prevents crashes after several connections-disconnections due to an limited amount of modbus TCP sockets
    available (3 or 4)
    """
    epc = _connections.get(ip)
    if epc is not None:
        try:
            epc.get_pv()
            return epc
        except Exception:
            try:
                epc.protocol.close_connection()
            except Exception:
                pass
    epc = EurothermEPC3008(ip)
    _connections[ip] = epc
    return epc

# This first class aims to implement the protocol used by EPC3008 devices (Modbus TCP).
class ModbusTCP :
    """Class of all the methods to communicate with an EPC 3008 device from creating the command
    to sending it and reading its response."""
    
    def __init__(self, ip : str):
        self._lock = threading.Lock()
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
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
            finally:
                self.client = None

    def read_holding_register(self, address: int, count: int = 1) -> list | None:
        """Reads holding register(s) from the device. Returns None if failed."""
        with self._lock:
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
        with self._lock:
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
    
class EurothermEPC3008:
    """Class for communicating with an EPC3008 instrument through Ethernet.
    It contains the methods I thought were essential as well as more complex ones aiming to
    facilitate the user's final experience.
    Temperature measured by the EPC is multiplied by 10. resolution_factor = 10 means
    that we want to devide the measure temp by 10 in order to get the correct value"""
    def __init__(self, ip: str, resolution_factor: int = 10):
        try:
            ip=ip.replace(" ", "")
            ipaddress.ip_address(ip)
        except ValueError as e:
            raise ValueError(f"Invalid IP address: {ip}") from e

        self.ip = ip
        self.resolution_factor = resolution_factor
        try:
            self.protocol = ModbusTCP(ip)
        except Exception as e:
            raise ConnectionError(f"Could not connect to {ip}: {e}") from e
        self.connected = True
        self.set_automatic_mode()

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

    #IO tab
    adr_sense = 12681
    
    # CT tab
    adr_leak_current = 1591
    
    # LOOP tab
    adr_mode_auto_manual = 273
    adr_target_sp = 2
    adr_working_sp = 5
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
        if resp is None:
            raise ConnectionError(f"Échec de lecture de la PV sur EPC3008 ({self.ip})")
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

    def get_working_sp(self) -> float:
        """Returns target set point value."""
        resp = self.protocol.read_holding_register(self.adr_working_sp)
        return self.protocol.decode_number(resp[0], self.resolution_factor)
    
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
        if not (isinstance(resp[0], int) and 0 <= resp[0] < len(list_values)):
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

