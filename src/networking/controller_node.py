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
            if isinstance(message, str):
                data = json.loads(message)
            else:
                data = message
            
            if data.get('type') == 'pot_data':
                # Extract incoming data
                timestamp = data['timestamp']
                pot_values = data['data']['pot_values']
                t_sin = data['data']['t_sin']
                t_cos = data['data']['t_cos']
                
                print(f"\nReceived pot data at {timestamp}")
                print("Incoming pot values (first 5):", pot_values[:5])
                
                if self.controller.current_state == MachineState.IDLE:
                    # Store incoming data in state handler
                    self.controller.state_handler.incoming_timestamp = timestamp
                    self.controller.state_handler.incoming_t_sin = t_sin
                    self.controller.state_handler.incoming_t_cos = t_cos
                    self.controller.state_handler.movement_buffer = pot_values
                    
                    # First drive wavemaker and collect energy
                    print("\nDriving wavemaker with pot values")
                    self.controller.transition_to(MachineState.DRIVE_WAVEMAKER)
                    await self.controller.handle_current_state()
                    
                    # Then prepare and send data
                    print("\nPreparing to send collected data")
                    self.controller.transition_to(MachineState.SEND_DATA)
                    data_packet = await self.controller.handle_current_state()
                    
                    if data_packet:
                        # Send to next node
                        dest = self.controller_config.get('destination')
                        if dest:
                            print(f"\nSending pot data to: {dest}")
                            await self.send_data_to(dest, data_packet)
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