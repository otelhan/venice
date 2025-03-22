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

class ControllerNode:
    def __init__(self, controller_name, port=8765):
        self.controller_name = controller_name
        self.port = port
        self.config = self._load_config()  # Full config with all controllers
        print("\nFull config loaded:", self.config)  # Debug print
        
        # Incoming buffer structure
        self.incoming_buffer = []  # List of movement arrays
        self.max_incoming_buffer = 6  # Reduced to 6 sets of movements
        self.max_movements_per_message = 30  # Each message has 30 values (20-127)
        
        # Get controller-specific config
        if self.config and 'controllers' in self.config:
            self.controller_config = self.config['controllers'].get(controller_name, {})
            print(f"\nController-specific config for {controller_name}:", self.controller_config)
            print(f"Destination: {self.controller_config.get('destination', 'None')}")
        else:
            self.controller_config = {}
            print("No controller config found!")
            
        # Initialize controller with both configs
        self.controller = MachineController(
            config=self.controller_config,  # Controller-specific config
            full_config=self.config        # Full config with all controllers
        )
        self.controller.node = self  # Give controller reference to this node
        
        self.mac = self.controller_config['mac']
        self.ip = self.controller_config['ip']
        
        print(f"\nController initialized:")
        print(f"- Name: {self.controller_name}")
        print(f"- MAC: {self.mac}")
        print(f"- IP: {self.ip}")
        print(f"- Display config: {self.controller_config.get('display', {})}")
        
        self.server = None
        self.current_connection = None  # Track the single active connection
        
        # Initialize to IDLE state
        self.controller.transition_to(MachineState.IDLE)
        
        self.uri = f"ws://localhost:{port}"
        self.connected_nodes = set()
        self.movement_data = []
        
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
        """Start the WebSocket server"""
        try:
            # Simple server setup - one connection at a time
            async with websockets.serve(
                self._handle_connection, 
                "0.0.0.0",  # Listen on all interfaces
                self.port,
                max_size=None,  # No message size limit
                max_queue=1     # Only queue one connection
            ) as server:
                self.server = server
                print(f"Controller {self.mac} listening on port {self.port}")
                await asyncio.Future()  # run forever
                
        except OSError as e:
            if e.errno == 48:  # Address already in use
                print(f"Port {self.port} is already in use. Trying to clean up...")
                await self.cleanup_port()
                await self.start()
            else:
                raise e
    
    async def cleanup_port(self):
        """Force cleanup of the port"""
        try:
            # Create a temporary socket to force port release
            temp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            temp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            temp_socket.bind(('localhost', self.port))
            temp_socket.close()
            await asyncio.sleep(1)  # Give time for OS to release the port
        except Exception as e:
            print(f"Error cleaning up port: {e}")
    
    async def stop(self):
        """Stop the WebSocket server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            await self.cleanup_port()
            print("Controller stopped")
    
    async def _handle_connection(self, websocket):
        """Handle websocket connection"""
        if self.current_connection is not None:
            print("Already handling a connection, rejecting new connection")
            await websocket.close(1013)  # Try to close gracefully
            return

        self.current_connection = websocket
        try:
            async for message in websocket:
                try:
                    await self.handle_message(websocket, message)
                    
                except Exception as e:
                    print(f"Error processing message: {e}")
                    await websocket.send(json.dumps({
                        "status": "error",
                        "message": str(e)
                    }))
                
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed normally")
        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            self.current_connection = None  # Clear the connection reference
    
    async def handle_message(self, websocket, message):
        """Handle incoming messages"""
        try:
            # Parse message data
            if isinstance(message, str):
                data = json.loads(message)
            else:
                data = message
            
            if data.get('type') == 'movement_data':
                # Extract incoming movement data
                timestamp = data['timestamp']
                pot_values = data['data']['pot_values']
                t_sin = data['data']['t_sin']
                t_cos = data['data']['t_cos']
                
                print(f"\nReceived movement data at {timestamp}")
                print("Incoming pot values (first 5):", pot_values[:5])
                
                if self.controller.current_state == MachineState.IDLE:
                    # Drive wavemaker with received pot values
                    print("\nDriving wavemaker with pot values")
                    self.controller.movement_buffer = pot_values
                    self.controller.transition_to(MachineState.DRIVE_WAVEMAKER)
                    await self.controller.handle_current_state()
                    
                    # Get energy values from camera
                    print("\nCollecting energy values from camera")
                    self.controller.transition_to(MachineState.COLLECT_SIGNAL)
                    energy_values = await self.controller.handle_current_state()
                    
                    if energy_values:
                        # Modulate energy with time encoding
                        print("\nModulating energy values with time encoding")
                        modulated_values = self.modulate_energy_with_time(energy_values, t_sin, t_cos)
                        
                        # Scale to pot range [20, 127]
                        print("\nScaling modulated energy to pot values")
                        min_val = min(modulated_values)
                        max_val = max(modulated_values)
                        new_pot_values = [
                            self.scale_movement_log(val, min_val, max_val) 
                            for val in modulated_values
                        ]
                        
                        # Prepare energy data packet
                        next_node_data = {
                            'type': 'energy_data',
                            'timestamp': timestamp,
                            'data': {
                                'pot_values': new_pot_values,  # Only send final pot values
                                't_sin': t_sin,
                                't_cos': t_cos
                            }
                        }
                        
                        # Send to next node
                        dest = self.controller_config.get('destination')
                        if dest:
                            print(f"\nSending energy data to: {dest}")
                            print("Outgoing pot values (first 5):", new_pot_values[:5])
                            self.controller.transition_to(MachineState.SEND_DATA)
                            await self.send_data_to(dest, next_node_data)
                else:
                    print(f"\nBuffering data - current state: {self.controller.current_state.name}")
                    if len(self.incoming_buffer) < self.max_incoming_buffer:
                        self.incoming_buffer.append(data)
                
                # Send acknowledgment
                response = {
                    'status': 'success',
                    'message': 'Movement data processed',
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
        if self.incoming_buffer and self.controller.current_state == MachineState.IDLE:
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
                self.controller.transition_to(new_state)
                self.controller.handle_current_state()
                return True
            else:
                print(f"Unknown command: {command}")
                return False
        except Exception as e:
            print(f"Error in execute_command: {e}")
            return False

    async def send_data_to(self, target_name, data):
        """Send data to another controller"""
        try:
            target = self.config['controllers'].get(target_name)
            if not target:
                print(f"Unknown target controller: {target_name}")
                return False
                
            target_port = target.get('port', 8765)  # Get configured port
            uri = f"ws://{target['ip']}:{target_port}"
            
            # Debug print data before sending
            print("\nPreparing to send data to", target_name)
            print("Target URI:", uri)
            print("Data format:")
            print("-" * 50)
            print("Type:", data.get('type'))
            print("Timestamp:", data.get('timestamp'))
            if 'data' in data:
                print("Data contents:")
                print("- pot_values (first 5):", data['data']['pot_values'][:5], "...")
                print("- t_sin:", data['data']['t_sin'])
                print("- t_cos:", data['data']['t_cos'])
            print("-" * 50)
            
            async with websockets.connect(uri) as websocket:
                await websocket.send(json.dumps(data))
                response = await websocket.recv()
                print(f"Response from {target_name}: {response}")
                return True
                
        except Exception as e:
            print(f"Error sending data: {str(e)}")
            print("Full data that failed to send:", json.dumps(data, indent=2))
            return False