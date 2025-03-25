from src.core.states import MachineState
from src.core.state_handlers import StateHandler
from src.core.camera_handler import CameraHandler
import serial
import serial.tools.list_ports
import asyncio
import websockets
import json

class MachineController:
    def __init__(self, config=None, full_config=None):
        """Initialize controller with config"""
        self.config = config or {}  # Default to empty dict if None
        self.full_config = full_config or {}
        self.current_state = MachineState.IDLE  # Initialize with IDLE
        self.last_state = None
        
        # Print config values
        print("\nController Configuration:")
        print(f"Full config: {self.config}")
        print(f"Display config: {self.config.get('display', {})}")
        print(f"Destination: {self.config.get('destination', 'None')}")
        
        # Initialize state handler with configs
        self.state_handler = StateHandler(
            controller=self,
            config=self.config,
            full_config=self.full_config
        )
        
        self.movement_buffer = []
        
        # Initialize serial connection
        if not self._init_serial():
            print("Warning: Failed to initialize serial connection")
        
        # Add retry counter and limit
        self.send_retries = 0
        self.max_retries = 3
        
        self.display_config = config.get('display', {}) if config else {}
        
        self.movement_buffer = []  # Store received movements
        self.serial = None
        if not self._init_serial():
            print("WARNING: Failed to initialize KB2040 connection")
        
    async def handle_current_state(self):
        """Handle the current state"""
        try:
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
                await self.state_handler.send_data()
            elif self.current_state == MachineState.IDLE:
                await self.state_handler.idle()
            # ... other states ...
            
        except Exception as e:
            print(f"Error handling state {self.current_state}: {e}")
            self.transition_to(MachineState.IDLE)
    
    def transition_to(self, new_state):
        """Transition to a new state"""
        print(f"\nTransitioning from {self.current_state.name} to {new_state.name}")
        self.last_state = self.current_state
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

    async def send_data_to(self, target_name, data):
        """Send data to another controller"""
        if hasattr(self, 'node'):
            return await self.node.send_data_to(target_name, data)
        else:
            print("Error: No node reference found")
            return False