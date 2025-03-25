import asyncio
import websockets
import json
import uuid
import time
import socket
import os
import yaml
import numpy as np
from src.core.machine_controller import MachineController
from src.core.states import MachineState
from src.core.config_handler import ConfigHandler
from datetime import datetime

class ControllerNode(MachineController):
    def __init__(self, controller_name, port=8765):
        # Load config first
        self.config = self._load_config()
        
        # Get controller-specific config
        if self.config and 'controllers' in self.config:
            self.controller_config = self.config['controllers'].get(controller_name, {})
            self.destination = self.controller_config.get('destination')
            print(f"\nController Details:")
            print(f"Name: {controller_name}")
            print(f"Destination: {self.destination}")
            print(f"Config: {self.controller_config}")
        else:
            print("No controller config found!")
            self.controller_config = {}
            
        # Initialize parent with proper config
        super().__init__(config=self.controller_config, full_config=self.config)
        
        # Controller node specific initialization
        self.controller_name = controller_name
        self.port = port
        self.mac = self.controller_config.get('mac', self._get_mac())
        self.ip = self.controller_config.get('ip', 'localhost')
        
        # Initialize buffers
        self.incoming_buffer = []
        self.max_incoming_buffer = 6
        self.max_movements_per_message = 30
        
        # Connection handling
        self.current_connection = None
        self.server = None
        
        # Initialize to IDLE state
        self.transition_to(MachineState.IDLE)
        
        self.max_retries = 3

    def _load_config(self):
        """Load configuration from YAML"""
        try:
            config_path = os.path.join('config', 'controllers.yaml')
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return None
    
    def _get_mac(self):
        return ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                        for elements in range(0,8*6,8)][::-1])
    
    async def start(self):
        """Start the controller node"""
        try:
            print(f"Controller {self.mac} listening on port {self.port}")
            
            async with websockets.serve(
                self._handle_connection,
                "0.0.0.0",
                self.port,
                ping_interval=None
            ) as server:
                self.server = server
                await asyncio.Future()  # run forever
                
        except Exception as e:
            print(f"Error starting controller: {e}")
            raise

    async def _handle_connection(self, websocket):
        """Handle incoming websocket connections"""
        try:
            # Store current connection
            self.current_connection = websocket
            
            async for message in websocket:
                await self.handle_message(websocket, message)
                
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed normally")
        except Exception as e:
            print(f"Error handling connection: {e}")
        finally:
            # Clear connection when done
            if self.current_connection == websocket:
                self.current_connection = None
    
    async def handle_message(self, websocket, message):
        """Handle incoming messages"""
        try:
            if isinstance(message, str):
                data = json.loads(message)
            else:
                data = message
            
            # If we're not in IDLE state, we're busy
            if self.current_state != MachineState.IDLE:
                print(f"\nBusy processing in state: {self.current_state.name}")
                response = {
                    'status': 'busy',
                    'message': f'Controller busy in state {self.current_state.name}'
                }
                await websocket.send(json.dumps(response))
                return
                
            # Handle message if we're ready...
            
            if data.get('type') == 'movement_data':
                # Extract data
                timestamp = data['timestamp']
                incoming_pot_values = data['data']['pot_values']
                t_sin = data['data']['t_sin']
                t_cos = data['data']['t_cos']
                
                print(f"\nReceived pot values at {timestamp}")
                print("Incoming pot values (first 5):", incoming_pot_values[:5])
                
                # Process data if in IDLE state
                if self.current_state == MachineState.IDLE:
                    # Store timing data
                    self.state_handler.outgoing_buffer.update({
                        'timestamp': timestamp,
                        't_sin': t_sin,
                        't_cos': t_cos
                    })
                    
                    print("\nStored timing data in buffer:")
                    print(f"Timestamp: {timestamp}")
                    print(f"t_sin: {t_sin}")
                    print(f"t_cos: {t_cos}")
                    
                    # Process through states
                    self.movement_buffer = incoming_pot_values
                    
                    # Drive wavemaker
                    self.transition_to(MachineState.DRIVE_WAVEMAKER)
                    await self.handle_current_state()
                    
                    # Send data to trainer
                    self.transition_to(MachineState.SEND_DATA)
                    await self.handle_current_state()
                    
                    # Return to IDLE to be ready for next data
                    self.transition_to(MachineState.IDLE)
                    
                else:
                    print(f"\nBuffering data - current state: {self.current_state.name}")
                    if len(self.incoming_buffer) < self.max_incoming_buffer:
                        self.incoming_buffer.append(data)
                
                # Send acknowledgment
                response = {
                    'status': 'success',
                    'message': 'Pot values processed',
                    'timestamp': timestamp
                }
                await websocket.send(json.dumps(response))
                
            else:
                # Handle other message types (discovery, etc.)
                message_type = data.get('type', '')
                if message_type == 'discovery':
                    await self.handle_discovery(websocket, data)
                elif message_type == 'connect':
                    await self.handle_connection(websocket, data)
                else:
                    print(f"Unknown message format: {data}")
                
        except Exception as e:
            print(f"Error handling message: {e}")
            error_response = {
                'status': 'error',
                'message': str(e)
            }
            await websocket.send(json.dumps(error_response))

    @staticmethod
    def modulate_energy_with_time(energy_values, t_sin, t_cos):
        """
        Modulates a list of energy values based on time encoding (t_sin and t_cos).
        
        Parameters:
            energy_values (list or np.array): List of 30 float energy values.
            t_sin (float): Time sine encoding in [-1, 1].
            t_cos (float): Time cosine encoding in [-1, 1].

        Returns:
            list: Modulated energy values (same length as input).
        """
        # Compute modulation factor based on time encoding
        # Modulation range will be [0.8, 1.2] across a full 24h cycle
        modulation_factor = 0.8 + 0.1 * t_sin + 0.1 * t_cos

        # Apply modulation to each energy value
        return [e * modulation_factor for e in energy_values]

    @staticmethod
    def scale_movement_log(raw_movement, min_value, max_value):
        """Applies logarithmic scaling and converts movement to [20, 127] for DS1841 control."""
        try:
            if max_value <= min_value:
                return 20
            log_scaled = np.log1p(raw_movement - min_value) / np.log1p(max_value - min_value)
            scaled = int(round(20 + log_scaled * (127 - 20)))
            return max(20, min(127, scaled))
        except Exception as e:
            print(f"Error scaling movement value: {e}")
            return 20

    def clear_incoming_buffer(self):
        """Clear the incoming message buffer"""
        buffer_size = len(self.incoming_buffer)
        self.incoming_buffer.clear()
        print(f"\nCleared incoming buffer ({buffer_size} sets of movements dropped)")

    async def process_buffer(self):
        """Process buffered messages when returning to IDLE"""
        if self.incoming_buffer and self.current_state == MachineState.IDLE:
            print(f"\nProcessing {len(self.incoming_buffer)} buffered sets of movements")
            message = self.incoming_buffer.pop(0)  # Get oldest set of movements
            await self.handle_message(message)  # message is already in correct format

    async def execute_command(self, command):
        """Execute a command"""
        print(f"Executing command: {command}")  # Debug log
        
        # Map commands to states
        command_to_state = {
            'd': MachineState.DRIVE_WAVEMAKER,
            'c': MachineState.COLLECT_SIGNAL,
            'i': MachineState.IDLE,
            'p': MachineState.PROCESS_DATA,
            's': MachineState.SEND_DATA,
            'r': MachineState.RECEIVE_DATA
        }
        
        try:
            if command in command_to_state:
                new_state = command_to_state[command]
                print(f"Transitioning to state: {new_state.name}")
                self.transition_to(new_state)
                self.handle_current_state()
                return True
            else:
                print(f"Unknown command: {command}")
                return False
        except Exception as e:
            print(f"Error in execute_command: {e}")
            return False

    async def send_to_destination(self, data):
        """Send data to destination"""
        try:
            target = self.config['controllers'].get(self.destination)
            if not target:
                print(f"Unknown destination: {self.destination}")
                return False
                
            # Always use port 8765 for controller communication
            port = 8765  # Force use of standard port for all controller communication
            uri = f"ws://{target['ip']}:{port}"
            
            print(f"\nSending to {self.destination} at {uri}")
            
            for attempt in range(self.max_retries):
                try:
                    print(f"Connecting to {self.destination} (attempt {attempt + 1}/{self.max_retries})")
                    async with websockets.connect(uri) as websocket:
                        await websocket.send(json.dumps(data))
                        response = await websocket.recv()
                        response_data = json.loads(response)
                        
                        if response_data.get('status') == 'success':
                            print(f"Data accepted by {self.destination}")
                            return True
                        else:
                            print(f"Error from {self.destination}:", response_data.get('message'))
                            
                except Exception as e:
                    print(f"Target {self.destination} is not reachable")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(1)
                        
            return False
                    
        except Exception as e:
            print(f"Error sending to {self.destination}: {e}")
            return False

    async def send_data(self):
        """Send data to destination"""
        try:
            if not self.destination:
                print("No destination configured!")
                return
                
            # Create data packet
            data = {
                'type': 'movement_data',
                'timestamp': self.state_handler.outgoing_buffer['timestamp'],
                'data': {
                    'pot_values': self.movement_buffer,
                    't_sin': self.state_handler.outgoing_buffer['t_sin'],
                    't_cos': self.state_handler.outgoing_buffer['t_cos']
                }
            }
            
            # Always use send_to_destination for ControllerNode
            success = await self.send_to_destination(data)
            
            if success:
                print("Data accepted by destination")
            else:
                print("Failed to send data")
                
            self.transition_to(MachineState.IDLE)
                
        except Exception as e:
            print(f"Error in send_data: {e}")
            self.transition_to(MachineState.IDLE)