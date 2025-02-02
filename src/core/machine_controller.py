from .states import MachineState
from .state_handlers import StateHandler
import serial
import serial.tools.list_ports

class MachineController:
    def __init__(self):
        self.current_state = None
        self.state_handler = StateHandler()
        self.movement_buffer = []  # Store received movements
        self.serial = None
        if not self._init_serial():
            print("WARNING: Failed to initialize KB2040 connection")
        
    def handle_current_state(self):
        """Handle the current state"""
        if self.current_state == MachineState.DRIVE_WAVEMAKER:
            # Pass movement buffer to state handler
            if self.movement_buffer and self.serial:
                self.state_handler.movement_buffer = self.movement_buffer
                self.state_handler.serial = self.serial  # Pass serial connection
                next_state = self.state_handler.drive_wavemaker()
                if next_state:
                    self.transition_to(MachineState.IDLE)
            else:
                print("ERROR: No movement data or KB2040 not connected")
                self.transition_to(MachineState.IDLE)
    
    def transition_to(self, new_state: MachineState):
        """Transition to a new state"""
        if self.current_state is None:
            print(f"Initializing state to: {new_state.name}")
        else:
            print(f"Transitioning from {self.current_state.name} to {new_state.name}")
        self.current_state = new_state

    def _init_serial(self):
        """Initialize serial connection to KB2040"""
        try:
            # Try different possible ports
            ports = [
                '/dev/ttyACM0',  # Common on Linux/Raspberry Pi
                '/dev/ttyACM1',
                '/dev/ttyUSB0',
                '/dev/ttyUSB1'
            ]
            
            for port in ports:
                try:
                    self.serial = serial.Serial(port, 9600, timeout=1)
                    print(f"Connected to KB2040 on {port}")
                    return True
                except serial.SerialException:
                    continue
                
            print("ERROR: KB2040 not found! Available ports:")
            for port in serial.tools.list_ports.comports():
                print(f"- {port.device}: {port.description}")
            return False
        
        except Exception as e:
            print(f"Error initializing serial: {e}")
            return False