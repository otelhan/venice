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
    def __init__(self, controller_name):
        self.controller_name = controller_name
        self.config = self._load_config()
        
        # Get controller-specific config
        if self.config and 'controllers' in self.config:
            self.controller_config = self.config['controllers'].get(controller_name, {})
            print(f"\nLoaded config for {controller_name}:")
            print(f"Controller config: {self.controller_config}")
        else:
            self.controller_config = {}
            print("No controller config found!")
            
        # Initialize controller with its config
        self.controller = MachineController(config=self.controller_config)
        
        self.mac = self.controller_config['mac']
        self.ip = self.controller_config['ip']
        
        print(f"Controller initialized:")
        print(f"- Name: {self.controller_name}")
        print(f"- MAC: {self.mac}")
        print(f"- IP: {self.ip}")
        
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
            self.server = await websockets.serve(
                self.handle_message, 
                "0.0.0.0",  # Listen on all interfaces
                self.port
            )
            print(f"Controller {self.mac} listening on port {self.port}")
            # Keep the server running
            while True:
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    break
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
    
    async def handle_message(self, websocket):
        """Handle incoming WebSocket messages"""
        try:
            async for message in websocket:
                print(f"\nReceived message: {message}")  # Debug log
                
                try:
                    data = json.loads(message)
                    message_type = data.get('type')
                    
                    if message_type == 'command':
                        command = data.get('command')
                        target_mac = data.get('mac')
                        
                        if target_mac == self.mac or target_mac == "00:00:00:00:00:00":
                            print(f"Executing command: {command}")
                            await self.execute_command(command)
                            response = {
                                "controller_name": self.controller_name,
                                "mac": self.mac,
                                "status": "success",
                                "message": f"Executed command: {command}"
                            }
                        else:
                            response = {
                                "controller_name": self.controller_name,
                                "mac": self.mac,
                                "status": "error",
                                "message": "MAC address mismatch"
                            }
                    elif message_type == 'data':
                        # Handle movement data
                        movements = data.get('data', {}).get('movements', [])
                        print(f"Received {len(movements)} movements")
                        
                        # Scale movements to motor range (20-127)
                        if movements:
                            # Store movements for driving wavemaker
                            self.controller.movement_buffer = movements
                            
                            # Automatically transition to DRIVE_WAVEMAKER state
                            print("Transitioning to DRIVE_WAVEMAKER state...")
                            self.controller.transition_to(MachineState.DRIVE_WAVEMAKER)
                            self.controller.handle_current_state()
                            
                            response = {
                                "controller_name": self.controller_name,
                                "mac": self.mac,
                                "status": "success",
                                "message": f"Received {len(movements)} movements and started wavemaker"
                            }
                        else:
                            response = {
                                "status": "error",
                                "message": "No movement data in packet"
                            }
                    elif message_type == 'status_request':
                        # Handle status request
                        response = {
                            "controller_name": self.controller_name,
                            "mac": self.mac,
                            "status": "success",
                            "state": self.controller.current_state.name if self.controller.current_state else "IDLE",
                            "uptime": time.time(),  # You could track actual uptime if needed
                            "message": "Controller is running"
                        }
                    else:
                        response = {
                            "controller_name": self.controller_name,
                            "mac": self.mac,
                            "status": "error",
                            "message": f"Unknown message type: {message_type}"
                        }
                    
                    print(f"Sending response: {response}")  # Debug log
                    await websocket.send(json.dumps(response))
                    
                except json.JSONDecodeError:
                    print("Error: Invalid JSON format")
                    
        except websockets.exceptions.ConnectionClosed:
            print("Client connection closed")
        except Exception as e:
            print(f"Error handling message: {e}")
    
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