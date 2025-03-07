import asyncio
import websockets
import json
import uuid
import time
import socket
import os
import yaml
from src.core.machine_controller import MachineController
from src.core.states import MachineState
from src.core.config_handler import ConfigHandler

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
        
        # Initialize to IDLE state
        self.controller.transition_to(MachineState.IDLE)
        
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
            # Updated to use newer websockets API
            async with websockets.serve(
                self._handle_connection, 
                "0.0.0.0",  # Listen on all interfaces
                self.port
            ) as server:
                self.server = server
                print(f"Controller {self.mac} listening on port {self.port}")
                await asyncio.Future()  # run forever
                
        except OSError as e:
            if e.errno == 48:  # Address already in use
                print(f"Port {self.port} is already in use. Trying to clean up...")
                await self.cleanup_port()
                # Try to start again
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
        """Handle websocket connection - removed path parameter"""
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    print(f"\nReceived message: {data['type']}")
                    
                    if not hasattr(self, 'movement_buffer'):
                        self.movement_buffer = []
                        
                    response = await self.handle_message(data)
                    await websocket.send(json.dumps(response))
                    
                    # Check buffer when returning to IDLE
                    if self.controller.current_state == MachineState.IDLE:
                        await self.process_buffer()
                        
                except json.JSONDecodeError as e:
                    print(f"Invalid JSON received: {e}")
                    await websocket.send(json.dumps({
                        "status": "error",
                        "message": "Invalid JSON format"
                    }))
                except KeyError as e:
                    print(f"Missing required field: {e}")
                    await websocket.send(json.dumps({
                        "status": "error",
                        "message": f"Missing field: {str(e)}"
                    }))
                except Exception as e:
                    print(f"Error processing message: {e}")
                    await websocket.send(json.dumps({
                        "status": "error",
                        "message": str(e)
                    }))
                
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")
        except Exception as e:
            print(f"Connection error: {e}")
    
    async def handle_message(self, message):
        """Handle incoming websocket message"""
        if message['type'] == 'data':
            movements = message['data']['movements']
            
            # Validate movement values
            if not all(20 <= x <= 127 for x in movements):
                return {"status": "error", "message": "Invalid movement values"}
                
            if len(movements) != self.max_movements_per_message:
                return {"status": "error", "message": "Invalid number of movements"}

            if self.controller.current_state == MachineState.IDLE:
                # Process immediately if IDLE
                self.controller.movement_buffer = movements
                self.controller.transition_to(MachineState.DRIVE_WAVEMAKER)
                await self.controller.handle_current_state()  # Await the async call
                return {"status": "ok"}
            else:
                # Buffer message if busy (except during SEND_DATA state)
                if self.controller.current_state != MachineState.SEND_DATA:
                    if len(self.incoming_buffer) < self.max_incoming_buffer:
                        print(f"\nController busy ({self.controller.current_state.name}), buffering movements")
                        self.incoming_buffer.append(movements)
                        print(f"Incoming buffer size: {len(self.incoming_buffer)}/{self.max_incoming_buffer}")
                        return {"status": "buffered"}
                    else:
                        print(f"\nIncoming buffer full ({self.max_incoming_buffer} sets), rejecting new movements")
                        return {"status": "rejected", "message": "Buffer full"}
                else:
                    print("\nIn SEND_DATA state, rejecting incoming movements")
                    return {"status": "rejected", "message": "In SEND_DATA state"}
        
        return {"status": "ok"}

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
            await self.handle_message({'type': 'data', 'data': {'movements': message}})

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
        target = self.config_handler.config['controllers'].get(target_name)
        if not target:
            print(f"Unknown target controller: {target_name}")
            return False
            
        try:
            uri = f"ws://{target['ip']}:{self.port}"
            async with websockets.connect(uri) as websocket:
                message = {
                    "type": "data",
                    "source": self.controller_name,
                    "data": data,
                    "timestamp": time.time()
                }
                await websocket.send(json.dumps(message))
                response = await websocket.recv()
                print(f"Response from {target_name}: {response}")
                return True
        except Exception as e:
            print(f"Error sending data to {target_name}: {e}")
            return False 