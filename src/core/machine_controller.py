from src.core.states import MachineState
from src.core.state_handlers import StateHandler
from src.core.camera_handler import CameraHandler
import serial
import serial.tools.list_ports
import asyncio

class MachineController:
    def __init__(self, config=None, full_config=None):
        self.current_state = None
        self.config = config or {}
        self.full_config = full_config or {}  # Store full config
        self.display_config = config.get('display', {}) if config else {}
        
        # Add retry counter and limit
        self.send_retries = 0
        self.max_retries = 3
        
        # Print config values
        print("\nController Configuration:")
        print(f"Full config: {self.config}")
        print(f"Display config: {self.display_config}")
        print(f"Destination: {self.config.get('destination', 'None')}")  # Print destination
        
        self.state_handler = StateHandler(
            display_config=self.display_config,
            controller_config=self.config,
            full_config=self.full_config  # Pass full config to StateHandler
        )
        self.movement_buffer = []  # Store received movements
        self.serial = None
        if not self._init_serial():
            print("WARNING: Failed to initialize KB2040 connection")
        
    async def handle_current_state(self):
        """Handle the current state"""
        print(f"\nHandling state: {self.current_state.name}")
        
        if self.current_state == MachineState.DRIVE_WAVEMAKER:
            if self.movement_buffer and self.serial:
                print(f"Movement buffer size: {len(self.movement_buffer)}")
                self.state_handler.movement_buffer = self.movement_buffer
                self.state_handler.serial = self.serial
                next_state = self.state_handler.drive_wavemaker()
                if next_state:
                    print("Transitioning to SEND_DATA")
                    if hasattr(self, 'node'):
                        self.node.clear_incoming_buffer()
                    self.transition_to(MachineState.SEND_DATA)
                    self.send_retries = 0
                    await self.handle_current_state()
                
        elif self.current_state == MachineState.SEND_DATA:
            dest = self.config.get('destination')
            if dest:
                print(f"\nAttempting to send data to {dest}")
                print(f"Current retry count: {self.send_retries}/{self.max_retries}")
                
                success = await self.state_handler.send_data(dest)
                if success:
                    print("Data accepted by destination")
                    self.send_retries = 0
                    print("Transitioning back to IDLE")
                    self.transition_to(MachineState.IDLE)
                    await asyncio.sleep(1)  # Give time for state change to settle
                    if hasattr(self, 'node'):
                        await self.node.process_buffer()
                else:
                    self.send_retries += 1
                    if self.send_retries >= self.max_retries:
                        print(f"Failed to send after {self.max_retries} attempts")
                        print("Transitioning back to IDLE")
                        self.transition_to(MachineState.IDLE)
                        await asyncio.sleep(1)  # Give time for state change to settle
                        if hasattr(self, 'node'):
                            await self.node.process_buffer()
                    else:
                        print(f"Retrying in 2 seconds... ({self.send_retries}/{self.max_retries})")
                        await asyncio.sleep(2)  # Wait before retry
                        await self.handle_current_state()
            else:
                print("\nNo destination configured in config!")
                print("Config:", self.config)
                print("Transitioning back to IDLE")
                self.transition_to(MachineState.IDLE)
                # Process any buffered messages
                if hasattr(self, 'node'):
                    await self.node.process_buffer()
    
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