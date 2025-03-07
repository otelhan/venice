import asyncio
import websockets
import json
import time
from src.core.video_processor import VideoProcessor
import numpy as np
import os
import cv2
import matplotlib.pyplot as plt
import yaml

class InputNode:
    def __init__(self, controller_port=8765):
        self.controller_port = controller_port
        self.processor = VideoProcessor()
        self.movement_buffer = []
        
        # Load config with correct path
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),  # Go up one more level
            'config', 
            'controllers.yaml'
        )
        print(f"Loading config from: {config_path}")  # Debug print
        
        try:
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)
                self.controllers = self.config.get('controllers', {})
                print(f"Loaded controllers: {list(self.controllers.keys())}")  # Debug print
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = None
            self.controllers = {}
        
    def get_controller_name(self, mac):
        """Get controller name from MAC address"""
        if not self.config:
            return "Unknown"
        for name, details in self.config['controllers'].items():
            if details['mac'].lower() == mac.lower():
                return name
        return "Unknown"
        
    def get_controller_mac(self, name):
        """Get MAC address from controller name"""
        if not self.config:
            return None
        if name in self.config['controllers']:
            return self.config['controllers'][name]['mac']
        return None
        
    async def discover_controllers(self):
        """Find available controllers"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                 'config', 'controllers.yaml')
        try:
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)
            
            print("\nDiscovering controllers...")
            for name, details in self.config['controllers'].items():
                mac = details['mac']
                current_ip = details.get('ip', 'Not set')
                last_seen = details.get('last_seen', 'Never')
                
                print(f"\nController: {name}")
                print(f"MAC: {mac}")
                print(f"Current IP: {current_ip}")
                print(f"Last seen: {last_seen}")
                
                # Allow IP update
                new_ip = input(f"Enter new IP for {name} (or press Enter to keep current): ").strip()
                if new_ip:
                    details['ip'] = new_ip
                    details['last_seen'] = time.time()
                    self.controllers[mac] = new_ip
                else:
                    self.controllers[mac] = current_ip
            
            # Save updated config
            with open(config_path, 'w') as f:
                yaml.safe_dump(self.config, f, default_flow_style=False)
                
        except Exception as e:
            print(f"Error discovering controllers: {e}")
            self.controllers["00:00:00:00:00:00"] = "localhost"
    
    async def send_command(self, controller_id, command):
        """Send command to controller"""
        if controller_id not in self.controllers:
            print(f"Unknown controller: {controller_id}")
            return
            
        ip = self.controllers[controller_id]
        uri = f"ws://{ip}:{self.controller_port}"
        print(f"Attempting to connect to {uri}")
        
        try:
            async with websockets.connect(uri, ping_interval=None) as websocket:
                message = {
                    "type": "command",
                    "command": command,
                    "controller_id": controller_id,
                    "mac": controller_id,
                    "timestamp": time.time()
                }
                print(f"Sending message: {message}")
                await websocket.send(json.dumps(message))
                try:
                    response = await websocket.recv()
                    print(f"Command response: {response}")
                    return json.loads(response)
                except websockets.exceptions.ConnectionClosed as e:
                    print(f"Connection closed while waiting for response: {e}")
        except Exception as e:
            print(f"Error sending command: {e}")
            
    async def send_data(self, controller_id, data):
        """Send data packet to controller"""
        if controller_id not in self.controllers:
            print(f"Unknown controller: {controller_id}")
            return
            
        ip = self.controllers[controller_id]
        uri = f"ws://{ip}:{self.controller_port}"
        
        try:
            # Increase timeout and disable ping to handle large data transfers
            async with websockets.connect(
                uri, 
                ping_interval=None,
                ping_timeout=None,
                close_timeout=30
            ) as websocket:
                message = {
                    "type": "data",
                    "data": data,
                    "controller_id": controller_id,
                    "timestamp": time.time()
                }
                print("Sending movement data...")
                await websocket.send(json.dumps(message))
                print("Waiting for response...")
                response = await websocket.recv()
                print(f"Data transmission response: {response}")
                return json.loads(response)
        except Exception as e:
            print(f"Error sending data: {e}")
            
    async def get_controller_status(self, controller_id):
        """Get status from controller"""
        if controller_id not in self.controllers:
            print(f"Unknown controller: {controller_id}")
            return
            
        ip = self.controllers[controller_id]
        uri = f"ws://{ip}:{self.controller_port}"
        
        try:
            async with websockets.connect(uri) as websocket:
                message = {
                    "type": "status_request",
                    "controller_id": controller_id,
                    "timestamp": time.time()
                }
                await websocket.send(json.dumps(message))
                response = await websocket.recv()
                return json.loads(response)
        except Exception as e:
            print(f"Error getting status: {e}")
            
    async def collect_movements(self):
        """Collect movement data from video"""
        print("\n=== Starting movement collection ===")
        
        # Reset video processor for new collection
        self.processor = VideoProcessor()  # Create new instance
        
        # Get the project root directory
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        video_path = os.path.join(project_root, "input_videos", "Ponte delle Guglie_day.mp4")
        print(f"Attempting to load video: {video_path}")
        
        try:
            # Get absolute path for debugging
            abs_path = os.path.abspath(video_path)
            print(f"Absolute path: {abs_path}")
            
            # Check if file exists
            if not os.path.exists(video_path):
                print(f"File does not exist at: {video_path}")
                return False
                
            # Try to load video with VideoProcessor
            try:
                self.processor.load_video(video_path)
            except ValueError as e:
                print(f"Failed to load video: {e}")
                # Print current working directory to help debug
                print(f"Current working directory: {os.getcwd()}")
                # List available files in input_videos directory
                try:
                    print("\nFiles in input_videos directory:")
                    files = os.listdir(os.path.join(project_root, "input_videos"))
                    for file in files:
                        full_path = os.path.join(project_root, "input_videos", file)
                        size = os.path.getsize(full_path)
                        print(f"- {file} ({size} bytes)")
                except Exception as e:
                    print(f"Could not list directory contents: {e}")
                return False
            
            print("\nVideo loaded successfully!")
            print("\nSelect ROI for analysis...")
            if not self.processor.select_roi():
                print("Failed to select ROI")
                return False
            
            # Collect for 10 seconds (300 frames at 30fps)
            print("\nCollecting movement data...")
            # Enable plot to see movement data in real-time
            movements = self.processor.calculate_movement(max_frames=300, show_plot=True)
            
            if movements:
                self.movement_buffer = movements
                print(f"\nCollected {len(movements)} measurements")
                plt.close('all')  # Close plot windows after collection

            
        except Exception as e:
            print(f"Error during movement collection: {e}")
            return False
        finally:
            cv2.destroyAllWindows()  # Ensure windows are closed
            plt.close('all')  # Ensure all plot windows are closed
        
    async def send_movement_data(self, controller_id):
        """Send movement data to a specific controller"""
        try:
            if not self.movement_buffer:
                print("No movement data to send!")
                return {"status": "error", "message": "No movement data"}
            
            uri = f"ws://{self.controllers[controller_id]['ip']}:8765"
            print(f"Connecting to {uri}")
            
            async with websockets.connect(uri) as websocket:
                data_packet = {
                    'type': 'data',
                    'data': {
                        'movements': self.movement_buffer
                    }
                }
                
                print(f"Sending {len(self.movement_buffer)} movements")
                await websocket.send(json.dumps(data_packet))
                
                try:
                    response = await websocket.recv()
                    response_data = json.loads(response)
                    print(f"Received response: {response_data}")
                    
                    if response_data.get('status') == 'rejected':
                        print(f"Message rejected by {controller_id}: {response_data.get('message')}")
                    elif response_data.get('status') == 'error':
                        print(f"Error from {controller_id}: {response_data.get('message')}")
                    else:
                        print(f"Message accepted by {controller_id}")
                        
                    return response_data
                    
                except json.JSONDecodeError as e:
                    print(f"Invalid response from server: {e}")
                    return {"status": "error", "message": "Invalid server response"}
                
        except websockets.exceptions.ConnectionClosed as e:
            print(f"WebSocket connection closed: {e.code} {e.reason}")
            return {"status": "error", "message": f"Connection closed: {e.reason}"}
        except Exception as e:
            print(f"Error sending to {controller_id}: {e}")
            return {"status": "error", "message": str(e)} 