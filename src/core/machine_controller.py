from src.core.states import MachineState
from src.core.state_handlers import StateHandler
from src.core.camera_handler import CameraHandler
import serial
import serial.tools.list_ports

class MachineController:
    def __init__(self, config=None):
        self.current_state = None
        self.config = config or {}
        self.display_config = config.get('display', {}) if config else {}
        
        # Print config values
        print("\nController Configuration:")
        print(f"Full config: {self.config}")
        print(f"Display config: {self.display_config}")
        
        self.state_handler = StateHandler(
            display_config=self.display_config,
            controller_config=self.config
        )
        self.movement_buffer = []  # Store received movements
        self.serial = None
        if not self._init_serial():
            print("WARNING: Failed to initialize KB2040 connection")
        
    async def handle_current_state(self):
        """Handle the current state"""
        print(f"\nHandling state: {self.current_state.name}")
        
        if self.current_state == MachineState.DRIVE_WAVEMAKER:
            next_state = await self.state_handler.drive_wavemaker()
            if next_state:
                self.transition_to(next_state)
            
        elif self.current_state == MachineState.SEND_DATA:
            next_state = await self.state_handler.send_data()
            if next_state:
                self.transition_to(next_state)
            
        elif self.current_state == MachineState.COLLECT_SIGNAL:
            result = self.state_handler.collect_signal()
            if result == 'd':
                self.transition_to(MachineState.DRIVE_WAVEMAKER)
            elif result == 'q':
                return 'q'
    
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