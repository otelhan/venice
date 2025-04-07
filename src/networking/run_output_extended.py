import asyncio
import websockets
import json
import numpy as np
from enum import Enum, auto
from src.networking.output_node import OutputNode
import yaml
import os
import math
from datetime import datetime
import csv
import pandas as pd
from pathlib import Path
import pytz  # For Venice timezone
import argparse
import sys

class OutputState(Enum):
    IDLE = auto()
    PREDICT = auto()
    ROTATE_CUBES = auto()
    SHOW_TIME = auto()
    TEST_MODE = auto()
    TEST_CLOCK_SECTOR = auto()  # New state for testing specific clock sectors
    START_POSITION = auto()  # New state for initial startup position

class OutputController:
    def __init__(self, mode='operation', port=8765, verbose=0):
        self.port = port
        self.current_state = OutputState.IDLE
        self.output_node = OutputNode()
        self.received_data = None
        self.clock_direction = 1  # 1 for increasing angle, -1 for decreasing
        self.clock_current_angle = 0
        self.mode = mode
        self.test_sector = 0  # For testing specific clock sectors
        
        # Test data
        self.test_data = None
        self.test_clock_angle = 0
        
        # Add Venice timezone
        self.venice_tz = pytz.timezone('Europe/Rome')  # Venice uses same timezone as Rome
        
        # Data storage
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Map each bin to a single servo
        self.servo_mapping = {
            1: 1,    # Bin 1 maps to servo 1
            2: 2,    # Bin 2 maps to servo 2
            3: 3,    # Bin 3 maps to servo 3
            4: 4,    # Bin 4 maps to servo 4
            5: 5     # Bin 5 maps to servo 5
        }
        
        # Track servo positions in degrees
        self.servo_positions = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}  # 0 degrees is center
        
        # Add clock position mapping (6 positions)
        self.clock_positions = {
            0: -150,  # 0-3 hours
            1: -90,   # 4-7 hours
            2: -30,   # 8-11 hours
            3: 30,    # 12-15 hours
            4: 90,    # 16-19 hours
            5: 150    # 20-23 hours
        }
        
        # If in test mode, load test data immediately
        if mode == 'test':
            self.load_test_data()
        
        self.verbose = verbose
        
        # Servos
        self.servo_controller = ServoController()
        self.servo_data = {}
        
        # WebSocket server
        self.server = None
        self.connected_clients = set()
        
        # Data receiving
        self.current_data = None
        self.current_timestamp = None
        self.pot_values = []
        self.t_sin = 0
        self.t_cos = 0
        
        # Clock
        self.clock_state = CLOCK_IDLE
        self.current_sector = 0
        self.sector_timestamps = {}
        
        # Test mode
        self.is_test_mode = (mode == 'test')

    def log(self, message, level=1):
        """Print log message if verbose level is high enough"""
        if self.verbose >= level:
            print(message)
            
    def debug(self, message):
        """Print debug message (level 2)"""
        self.log(message, level=2)

    def load_test_data(self):
        """Load test data package"""
        test_data = {
            "type": "movement_data",
            "timestamp": "2025-03-30 23:44:57.831136",
            "data": {
                "pot_values": [
                    123, 126, 100, 108, 124, 125, 77, 61, 127, 126,
                    120, 109, 125, 125, 20, 20, 110, 110, 20, 20,
                    108, 108, 25, 28, 20, 107, 106, 23, 29, 20
                ],
                "t_sin": 0.8313819709444351,
                "t_cos": 0.5557013751904403
            }
        }
        self.test_data = test_data
        return test_data

    def calculate_clock_angle(self, t_sin, t_cos):
        """Calculate clock angle from sine and cosine values"""
        # Calculate angle in radians using arctangent2
        angle_rad = math.atan2(t_sin, t_cos)
        # Convert to degrees
        angle_deg = math.degrees(angle_rad)
        # Scale to our -150 to 150 range
        scaled_angle = (angle_deg / 180.0) * 150
        return scaled_angle

    async def center_all_servos(self):
        """Center all servos to their neutral positions (0 degrees)"""
        print("\n=== Centering All Servos ===")
        
        # Center cube servos (main controller)
        for servo_id in range(1, 6):
            command = {
                'type': 'servo',
                'controller': 'main',
                'servo_id': servo_id,
                'position': 1500,  # Center position in microseconds
                'time_ms': 1000
            }
            response = self.output_node.process_command(command)
            if response['status'] == 'ok':
                print(f"✓ Centered cube servo {servo_id}")
                self.servo_positions[servo_id] = 0  # Track in degrees
            else:
                print(f"✗ Failed to center cube servo {servo_id}")
            await asyncio.sleep(0.1)
        
        # Center clock servo (secondary controller)
        clock_command = {
            'type': 'servo',
            'controller': 'secondary',
            'servo_id': 1,
            'position': 1500,  # Center position in microseconds
            'time_ms': 1000
        }
        response = self.output_node.process_command(clock_command)
        if response['status'] == 'ok':
            print(f"✓ Centered clock servo")
            self.clock_current_angle = 0  # Track in degrees
        else:
            print(f"✗ Failed to center clock servo")
        
        print("=== All Servos Centered ===")
        print("\nWaiting 3 seconds...")
        await asyncio.sleep(3)  # Wait 3 seconds after centering
        print("Wait complete, proceeding...")

    async def start(self):
        """Start the websocket server and initializes servos"""
        try:
            if self.verbose >= 1:
                print(f"\nStarting output controller in {self.mode} mode")
                print(f"Listening on port {self.port}")
                
            # Initialize and center all servos
            await self.center_all_servos()
            
            # Different behavior based on mode
            if self.mode == 'operation':
                if self.verbose >= 1:
                    print("\nStarting WebSocket server...")
                # Start WebSocket server in operation mode
                self.server = await websockets.serve(
                    self.handle_client, 
                    "0.0.0.0",  # Listen on all interfaces
                    self.port,
                    ping_interval=None,  # Disable ping
                    ping_timeout=None    # Disable ping timeout
                )
                
                if self.verbose >= 1:
                    print(f"WebSocket server running on port {self.port}")
                    print("Waiting for connections...")
                
                # Keep the server running
                await self.server.wait_closed()
            else:
                # In test mode, enter the main test loop
                await self.main_loop()
            
            return True
        except Exception as e:
            print(f"Error starting output controller: {e}")
            import traceback
            traceback.print_exc()
            return False
            
    async def stop(self):
        """Stop the websocket server and cleanup"""
        try:
            if self.verbose >= 1:
                print("\nStopping output controller...")
            
            # Close all client connections
            for client in self.connected_clients.copy():
                try:
                    await client.close()
                except:
                    pass
            
            # Close the server if it exists
            if self.server:
                self.server.close()
                await self.server.wait_closed()
                
            # Center all servos before exit
            await self.center_all_servos()
            
            if self.verbose >= 1:
                print("Output controller stopped")
            return True
        except Exception as e:
            print(f"Error stopping output controller: {e}")
            return False

    async def handle_client(self, websocket, path):
        """Handle new client connections"""
        try:
            # Keep track of connected clients
            self.connected_clients.add(websocket)
            client_ip = websocket.remote_address[0] if hasattr(websocket, "remote_address") else "unknown"
            
            if self.verbose >= 1:
                print(f"\nNew connection from: {client_ip}")
            
            try:
                async for message in websocket:
                    try:
                        # Parse the message as JSON
                        data = json.loads(message)
                        
                        if self.verbose >= 2:  # Only in debug mode
                            print(f"\nReceived data: {data}")
                        else:
                            # Minimal message in normal mode
                            message_type = data.get('type', 'unknown')
                            timestamp = data.get('timestamp', 'none')
                            if self.verbose >= 1:
                                print(f"\nReceived {message_type} message with timestamp {timestamp}")
                        
                        # Handle different message types
                        if data.get('type') == 'movement_data':
                            # Process movement data 
                            await self.process_movement_data(data)
                    except json.JSONDecodeError:
                        if self.verbose >= 1:
                            print(f"Received invalid JSON message: {message[:100]}...")
                    except Exception as e:
                        if self.verbose >= 1:
                            print(f"Error processing message: {e}")
            except websockets.exceptions.ConnectionClosed:
                if self.verbose >= 1:
                    print(f"Connection with {client_ip} closed")
            finally:
                # Remove client from connected set
                self.connected_clients.remove(websocket)
                if self.verbose >= 1:
                    print(f"Client {client_ip} disconnected")
        except Exception as e:
            if self.verbose >= 1:
                print(f"Error in client handler: {e}")

    async def process_movement_data(self, data):
        """Process movement data received from controller"""
        try:
            # Extract timestamp and movement data
            self.current_timestamp = data.get('timestamp', '')
            
            # Extract pot values and time encoding
            pot_data = data.get('data', {})
            self.pot_values = pot_data.get('pot_values', [])
            self.t_sin = pot_data.get('t_sin', 0)
            self.t_cos = pot_data.get('t_cos', 0)
            
            # Check if we have valid data
            if not self.pot_values:
                if self.verbose >= 1:
                    print(f"Received empty pot values")
                return
                
            if self.verbose >= 1:
                print(f"Received {len(self.pot_values)} pot values")
                print(f"Time encoding: sin={self.t_sin:.2f}, cos={self.t_cos:.2f}")
            
            # Set current data
            self.current_data = data
            
            # Change state to predict
            old_state = self.current_state
            self.current_state = OutputState.PREDICT
            
            if self.verbose >= 1:
                print(f"State transitioning from {old_state.name} to {self.current_state.name}")
                
            # Handle the current state (this will process the prediction)
            await self.handle_current_state()
        except Exception as e:
            if self.verbose >= 1:
                print(f"Error processing movement data: {e}")

    async def handle_current_state(self):
        """Handle the current state"""
        if self.current_state == OutputState.START_POSITION:
            print("\n=== Starting Position ===")
            if self.mode == 'operation':
                print("Ready to receive data")
                print("Waiting 3 seconds...")
                await asyncio.sleep(3)
                print("Wait complete, proceeding...")
                
                # Transition to IDLE state
                self.current_state = OutputState.IDLE
                print("Transitioning to IDLE mode, ready to receive data...")
                print("Waiting for data...")
                
                # For operation mode, start websocket server and never return
                server = await websockets.serve(
                    self.handle_client, 
                    "0.0.0.0", 
                    self.port,
                    ping_interval=None,
                    ping_timeout=None
                )
                print(f"Websocket server running on port {self.port}")
                await server.wait_closed()  # This will block until the server is closed
                
            else:
                print("The clock is centered at 0 degrees")
                print("Press Enter to continue to menu...")
                input()
                await self.transition_to(OutputState.IDLE)
            
        elif self.current_state == OutputState.IDLE:
            print("Waiting for data...")
            
            if self.mode == 'test':
                await self.handle_test_menu()

        elif self.current_state == OutputState.PREDICT:
            print("Predicting (placeholder - waiting 3 seconds)")
            if self.mode == 'operation':
                await self.center_all_servos_for_operation()
            await asyncio.sleep(3)
            await self.transition_to(OutputState.ROTATE_CUBES)

        elif self.current_state == OutputState.ROTATE_CUBES:
            if self.received_data:
                await self.rotate_cubes(self.received_data)
                self.received_data = None
                await self.transition_to(OutputState.SHOW_TIME)
                
        elif self.current_state == OutputState.SHOW_TIME:
            timestamp = None
            if self.test_data and 'timestamp' in self.test_data:
                timestamp = self.test_data['timestamp']
            
            await self.move_clock()
            
            if self.mode == 'operation' and timestamp:
                success = await self.send_acknowledgement(timestamp)
                if success:
                    print("Acknowledgment sent to video_input")
                else:
                    print("Failed to send acknowledgment to video_input")
            
            await self.transition_to(OutputState.IDLE)
            
        elif self.current_state == OutputState.TEST_MODE:
            if self.test_data:
                data = self.test_data['data']
                pot_values = data['pot_values']
                
                await self.move_clock()
                
                await self.rotate_cubes(pot_values)
                
                await self.transition_to(OutputState.IDLE)
            else:
                print("No test data available")
                await self.transition_to(OutputState.IDLE)
                
        elif self.current_state == OutputState.TEST_CLOCK_SECTOR:
            await self.move_clock_to_sector(self.test_sector)
            await self.transition_to(OutputState.IDLE)

    async def print_servo_positions(self):
        """Print current position of all servos"""
        print("\nCurrent Servo Positions:")
        print("------------------------")
        for servo_id, angle in self.servo_positions.items():
            print(f"Servo {servo_id}: {angle:.1f}°")
        print("------------------------")

    async def rotate_cubes(self, data):
        """Rotate servos based on histogram bin averages"""
        print(f"\n=== Processing {len(data)} values into 5 bins ===")
        print("Input values:", data)
        
        # Create histogram bins for 5 servos
        bins = np.linspace(20, 127, 6)
        bin_indices = np.digitize(data, bins) - 1
        
        print("\nBin ranges:")
        for i in range(len(bins)-1):
            print(f"Bin {i+1}: {bins[i]:.1f} to {bins[i+1]:.1f}")
        
        # Load servo config
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config', 'controllers.yaml')
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                servo_config = config.get('servo_config', {})
                main_controller = servo_config.get('controllers', {}).get('main', {})
                servos = main_controller.get('servos', {})
        except Exception as e:
            print(f"Warning: Could not load servo config: {e}")
            servos = {}
        
        print("\n=== Moving Cube Servos ===")
        # Move all cube servos
        for bin_num in range(5):
            bin_values = [val for val, idx in zip(data, bin_indices) if idx == bin_num]
            servo_id = self.servo_mapping[bin_num + 1]
            
            print(f"\nServo {servo_id} (Bin {bin_num + 1}):")
            print(f"Values in bin: {bin_values}")
            
            if bin_values:
                bin_avg = sum(bin_values) / len(bin_values)
                # Scale from input range (20-127) to angle range (-150 to 150)
                angle = ((bin_avg - 20) / (127 - 20)) * 300 - 150
                
                # Get servo config
                servo_config = servos.get(str(servo_id), {})
                min_angle = servo_config.get('min_angle', -150.0)
                max_angle = servo_config.get('max_angle', 150.0)
                
                # Clamp angle to configured limits
                angle = max(min_angle, min(max_angle, angle))
                
                print(f"Bin average: {bin_avg:.1f}")
                print(f"Calculated angle: {angle:.1f}°")
                print(f"Servo limits: {min_angle}° to {max_angle}°")
                
                command = {
                    'type': 'servo',
                    'controller': 'main',
                    'servo_id': servo_id,
                    'position': angle,
                    'time_ms': 1000
                }
                
                response = self.output_node.process_command(command)
                if response['status'] == 'ok':
                    print(f"✓ Servo {servo_id} moved to {angle:.1f}°")
                    self.servo_positions[servo_id] = angle
                else:
                    print(f"✗ Failed to move servo {servo_id}")
                await asyncio.sleep(0.1)
            else:
                print("No values in this bin")
        
        print("\n=== Cube Movement Complete ===")
        print("Final servo positions:")
        await self.print_servo_positions()
        return True

    def get_time_sector(self, t_sin, t_cos):
        """
        Convert t_sin and t_cos to hour (0-23) and then map to one of 6 positions
        Returns: (hour, sector, angle)
        """
        # Calculate angle in radians and convert to hours
        angle_rad = math.atan2(t_sin, t_cos)
        hours = ((angle_rad + math.pi) * 12 / math.pi) % 24
        
        # Map hours to sectors (4-hour blocks)
        sector = int(hours / 4)  # 0-5 (6 sectors)
        angle = self.clock_positions[sector]
        
        return hours, sector, angle

    async def move_clock(self):
        """Move clock servo to position based on time"""
        print("\n=== Moving Clock Servo ===")
        
        if not self.test_data:
            print("No time data available")
            return False
            
        # Get time values from test data
        data = self.test_data['data']
        t_sin = data['t_sin']
        t_cos = data['t_cos']
        
        # Calculate target position
        hours, sector, target_angle = self.get_time_sector(t_sin, t_cos)
        print(f"Time reference: {hours:.1f} hours")
        print(f"Mapped to sector {sector}/5 ({sector * 4}-{(sector + 1) * 4} hours)")
        print(f"Current angle: {self.clock_current_angle:.1f}°")
        print(f"Target angle: {target_angle:.1f}°")
        
        if self.mode == 'operation':
            # In operation mode, always center at sector 5 (150 degrees) first
            center_command = {
                'type': 'servo',
                'controller': 'secondary',
                'servo_id': 1,
                'position': 150,  # Sector 5 (150 degrees)
                'time_ms': 1000
            }
            print("Moving to sector 5 (150°)...")
        else:
            # In test mode, center at 0 degrees
            center_command = {
                'type': 'servo',
                'controller': 'secondary',
                'servo_id': 1,
                'position': 0,  # 0 degrees is center (will be converted to microseconds)
                'time_ms': 1000
            }
            print("Moving to center position (0°)...")
        
        response = self.output_node.process_command(center_command)
        if response['status'] == 'ok':
            if self.mode == 'operation':
                print("✓ Clock positioned at sector 5 (150°)")
                self.clock_current_angle = 150
            else:
                print("✓ Clock centered")
                self.clock_current_angle = 0
            await asyncio.sleep(3)  # Wait 3 seconds at center/position
        else:
            print("✗ Failed to position clock servo")
            return False
        
        # In test mode, perform full rotation; in operation mode, go directly to target
        if self.mode == 'test':
            # Perform one full rotation
            print("\nPerforming full rotation...")
            rotation_angles = [-150, -90, -30, 30, 90, 150, -150]  # Complete cycle
            for angle in rotation_angles:
                rotation_command = {
                    'type': 'servo',
                    'controller': 'secondary',
                    'servo_id': 1,
                    'position': angle,  # Angle in degrees (will be converted to microseconds)
                    'time_ms': 500  # Faster movement for rotation
                }
                
                response = self.output_node.process_command(rotation_command)
                if response['status'] == 'ok':
                    print(f"✓ Rotated to {angle}°")
                    self.clock_current_angle = angle
                    await asyncio.sleep(0.6)  # Short delay between positions
                else:
                    print(f"✗ Failed to rotate to {angle}°")
                    return False
        
        # Move to target position
        print(f"\nMoving to final position in sector {sector}...")
        clock_command = {
            'type': 'servo',
            'controller': 'secondary',
            'servo_id': 1,
            'position': target_angle,  # Angle in degrees (will be converted to microseconds)
            'time_ms': 1000
        }
        
        response = self.output_node.process_command(clock_command)
        if response['status'] == 'ok':
            print(f"✓ Clock moved to sector {sector} ({target_angle:.1f}°)")
            self.clock_current_angle = target_angle
        else:
            print("✗ Failed to move clock servo")
            return False
        
        # Wait at target position
        wait_time = 7  # seconds to wait at target position
        print(f"\nWaiting at sector {sector} for {wait_time} seconds...")
        await asyncio.sleep(wait_time)
        
        # In operation mode, return to sector 5 after waiting
        if self.mode == 'operation':
            print("\nReturning to sector 5 (150°)...")
            return_command = {
                'type': 'servo',
                'controller': 'secondary',
                'servo_id': 1,
                'position': 150,  # Return to sector 5
                'time_ms': 1000
            }
            
            response = self.output_node.process_command(return_command)
            if response['status'] == 'ok':
                print("✓ Clock returned to sector 5 (150°)")
                self.clock_current_angle = 150
            else:
                print("✗ Failed to return clock to sector 5")
                return False
            
            # Brief wait after returning
            await asyncio.sleep(1.1)
        
        print("=== Clock Movement Sequence Complete ===")
        return True

    async def send_acknowledgement(self, timestamp):
        """Send acknowledgement back to video_input"""
        try:
            if self.verbose >= 1:
                print("\n=== Sending Acknowledgment to Video Input ===")
            
            # Get video_input configuration
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                    'config', 'controllers.yaml')
            if self.verbose >= 1:
                print(f"Loading config from: {config_path}")
            
            try:
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                if self.verbose >= 1:
                    print("Config loaded successfully")
            except Exception as e:
                if self.verbose >= 1:
                    print(f"Failed to load config: {e}")
                return False
            
            # Print entire video_input config for debugging
            video_input_config = config.get('video_input', {})
            if self.verbose >= 2:  # Only in debug mode
                print(f"\nVideo input config: {video_input_config}")
            
            if not video_input_config:
                if self.verbose >= 1:
                    print("No video_input configuration found in config file")
                return False
            
            # Connect to video_input's IP and listen_port
            video_ip = video_input_config.get('ip')
            if not video_ip:
                if self.verbose >= 1:
                    print("No IP address defined for video_input in config")
                return False
                
            video_listen_port = video_input_config.get('listen_port')
            if not video_listen_port:
                if self.verbose >= 1:
                    print("No listen_port defined for video_input in config")
                video_listen_port = 8777  # Default port
            
            uri = f"ws://{video_ip}:{video_listen_port}"
            if self.verbose >= 1:
                print(f"Acknowledgment URI: {uri}")
            
            # Try to ping the target IP first to verify connectivity
            if self.verbose >= 1:
                try:
                    import subprocess
                    ping_result = subprocess.run(
                        ["ping", "-c", "1", "-W", "2", video_ip], 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE
                    )
                    if ping_result.returncode == 0:
                        print(f"✓ Host {video_ip} is reachable")
                    else:
                        print(f"⚠ WARNING: Host {video_ip} did not respond to ping")
                except Exception as e:
                    print(f"Failed to ping host: {e}")
                
                # Try checking if port is open
                try:
                    import socket
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    result = sock.connect_ex((video_ip, int(video_listen_port)))
                    if result == 0:
                        print(f"✓ Port {video_listen_port} is open on {video_ip}")
                    else:
                        print(f"⚠ WARNING: Port {video_listen_port} appears to be closed on {video_ip}")
                    sock.close()
                except Exception as e:
                    print(f"Port check failed: {e}")
            
            # Add retry logic
            max_retries = 3
            retry_delay = 2  # seconds
            
            for attempt in range(max_retries):
                try:
                    if self.verbose >= 1:
                        print(f"\nAttempt {attempt+1}/{max_retries} to send acknowledgment")
                    
                    # Use more lenient timeout settings
                    async with asyncio.timeout(5):
                        async with websockets.connect(
                            uri,
                            ping_interval=None,
                            ping_timeout=None,
                            close_timeout=2.0
                        ) as websocket:
                            if self.verbose >= 1:
                                print(f"✓ Connected to video_input at {uri}")
                            
                            # Create acknowledgment message - IMPORTANT: Must have 'type': 'ack'
                            ack = {
                                'type': 'ack',  # Must be exactly 'ack'
                                'timestamp': timestamp,
                                'status': 'success',
                                'message': 'Clock movement complete'
                            }
                            
                            # Log the exact message we're sending for debugging
                            ack_json = json.dumps(ack)
                            if self.verbose >= 2:
                                print(f"Sending ack: {ack_json}")
                            
                            # Send the acknowledgment
                            await websocket.send(ack_json)
                            if self.verbose >= 1:
                                print("✓ Acknowledgment JSON sent successfully")
                            
                            # Wait briefly for any response (optional but helpful for debugging)
                            if self.verbose >= 1:
                                try:
                                    response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                                    print(f"Received response: {response}")
                                except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                                    # No response is expected, so this is fine
                                    print("No response received (this is normal)")
                                
                            # Keep connection open a little longer to ensure message is received
                            await asyncio.sleep(1)
                            if self.verbose >= 1:
                                print("Acknowledgment completed successfully")
                            return True
                            
                except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                    error_type = "Timeout" if isinstance(e, asyncio.TimeoutError) else "Connection closed"
                    if self.verbose >= 1:
                        print(f"× {error_type} on attempt {attempt+1}: {str(e) or 'No details'}")
                    
                    if attempt < max_retries - 1:
                        if self.verbose >= 1:
                            print(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                    else:
                        if self.verbose >= 1:
                            print("All retry attempts failed")
                        
                except Exception as e:
                    if self.verbose >= 1:
                        print(f"× Unexpected error on attempt {attempt+1}: {e}")
                        if self.verbose >= 2:
                            import traceback
                            traceback.print_exc()
                    
                    if attempt < max_retries - 1:
                        if self.verbose >= 1:
                            print(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                    else:
                        if self.verbose >= 1:
                            print("All retry attempts failed")
            
            if self.verbose >= 1:
                print("=== Failed to send acknowledgment ===")
            return False
            
        except Exception as e:
            if self.verbose >= 1:
                print(f"× Error in acknowledgment process: {e}")
                if self.verbose >= 2:
                    import traceback
                    traceback.print_exc()
            return False

    def stop(self):
        """Stop and cleanup the controller"""
        print("\nStopping controller...")
        # Close each controller's connection
        for name, controller in self.output_node.controllers.items():
            print(f"Closing {name} controller...")
            controller.close()
        print("Controller stopped")

    def get_venice_time(self):
        """Get current time in Venice timezone"""
        utc_now = datetime.now(pytz.utc)
        venice_now = utc_now.astimezone(self.venice_tz)
        return venice_now
        
    def get_csv_path(self):
        """Get CSV path with date-based rotation"""
        # Get current Venice time and format date string
        venice_time = self.get_venice_time()
        date_str = venice_time.strftime('%Y%m%d')
        
        # Return full path with date
        return os.path.join(self.data_dir, f"processed_movement_{date_str}.csv")
        
    def save_to_csv(self, data):
        """Save received data to CSV"""
        try:
            # Extract data from the message
            timestamp = data.get('timestamp')
            pot_values = data['data']['pot_values']
            t_sin = data['data']['t_sin']
            t_cos = data['data']['t_cos']
            
            # Create row data dictionary
            row_data = {
                'timestamp': timestamp,
                **{f'pot_value_{i}': val for i, val in enumerate(pot_values)},
                't_sin': t_sin,
                't_cos': t_cos
            }
            
            # Convert to DataFrame
            df = pd.DataFrame([row_data])
            
            # Get CSV file path
            csv_path = self.get_csv_path()
            print(f"\nSaving data to CSV file: {csv_path}")
            
            # Check if file exists to decide whether to write header
            file_exists = os.path.exists(csv_path)
            
            # Save to CSV
            if file_exists:
                # Append without header
                df.to_csv(csv_path, mode='a', header=False, index=False)
            else:
                # Create new file with header
                df.to_csv(csv_path, index=False)
                
            print(f"Successfully saved data to {csv_path}")
            return True
            
        except Exception as e:
            print(f"Error saving to CSV: {e}")
            return False

    async def move_clock_to_sector(self, sector):
        """Move clock directly to a specified sector (0-5)"""
        print(f"\n=== Moving Clock to Sector {sector} ===")
        
        if sector < 0 or sector > 5:
            print("Error: Sector must be between 0 and 5")
            return False
            
        # Get angle for the requested sector
        target_angle = self.clock_positions[sector]
        print(f"Sector {sector}: {sector * 4}-{(sector + 1) * 4} hours")
        print(f"Current angle: {self.clock_current_angle:.1f}°")
        print(f"Target angle: {target_angle:.1f}°")
        
        # First return to center
        center_command = {
            'type': 'servo',
            'controller': 'secondary',
            'servo_id': 1,
            'position': 0,  # 0 degrees is center (will be converted to microseconds)
            'time_ms': 1000
        }
        
        print("Moving to center position...")
        response = self.output_node.process_command(center_command)
        if response['status'] == 'ok':
            print("✓ Clock centered")
            self.clock_current_angle = 0
            await asyncio.sleep(1)  # Wait 1 second at center
        else:
            print("✗ Failed to center clock servo")
            return False
        
        # Move directly to target position
        clock_command = {
            'type': 'servo',
            'controller': 'secondary',
            'servo_id': 1,
            'position': target_angle,  # Angle in degrees (will be converted to microseconds)
            'time_ms': 1000
        }
        
        response = self.output_node.process_command(clock_command)
        if response['status'] == 'ok':
            print(f"✓ Clock moved to sector {sector} ({target_angle:.1f}°)")
            self.clock_current_angle = target_angle
        else:
            print("✗ Failed to move clock servo")
            return False
        
        await asyncio.sleep(1)
        print("=== Clock Move Complete ===")
        return True

    async def move_clock_to_angle(self, angle):
        """Move clock directly to a specified angle between -150 and 150 degrees"""
        print(f"\n=== Moving Clock to {angle:.1f}° ===")
        
        if angle < -150 or angle > 150:
            print("Error: Angle must be between -150 and 150 degrees")
            return False
            
        print(f"Current angle: {self.clock_current_angle:.1f}°")
        print(f"Target angle: {angle:.1f}°")
        
        # First return to center
        center_command = {
            'type': 'servo',
            'controller': 'secondary',
            'servo_id': 1,
            'position': 0,  # 0 degrees is center (will be converted to microseconds)
            'time_ms': 1000
        }
        
        print("Moving to center position...")
        response = self.output_node.process_command(center_command)
        if response['status'] == 'ok':
            print("✓ Clock centered")
            self.clock_current_angle = 0
            await asyncio.sleep(1)  # Wait 1 second at center
        else:
            print("✗ Failed to center clock servo")
            return False
        
        # Move directly to target angle
        clock_command = {
            'type': 'servo',
            'controller': 'secondary',
            'servo_id': 1,
            'position': angle,  # Angle in degrees (will be converted to microseconds)
            'time_ms': 1000
        }
        
        response = self.output_node.process_command(clock_command)
        if response['status'] == 'ok':
            print(f"✓ Clock moved to {angle:.1f}°")
            self.clock_current_angle = angle
        else:
            print("✗ Failed to move clock servo")
            return False
        
        await asyncio.sleep(1)
        print("=== Clock Move Complete ===")
        return True
        
    async def handle_test_menu(self):
        """Handle test mode menu"""
        print("\n=== Test Mode Menu ===")
        print("1. Load sample data and process")
        print("2. Test clock sector movement")
        print("3. Reset all servos to center")
        print("4. Set clock to custom position")
        print("5. Help - Clock sectors explanation")
        print("6. Exit test mode")
        
        choice = input("\nEnter your choice (1-6): ").strip()
        
        if choice == '1':
            # Load test data and process
            self.load_test_data()
            await self.transition_to(OutputState.TEST_MODE)
            
        elif choice == '2':
            # Test clock sector movement
            print("\nSelect clock sector to move to:")
            print("-------------------------------")
            print("Sector | Time Range | Angle")
            print("-------------------------------")
            print("0      | 00-03 hrs  | -150°")
            print("1      | 04-07 hrs  | -90°")
            print("2      | 08-11 hrs  | -30°")
            print("3      | 12-15 hrs  | +30°")
            print("4      | 16-19 hrs  | +90°")
            print("5      | 20-23 hrs  | +150°")
            print("-------------------------------")
            
            sector_choice = input("\nEnter sector (0-5): ").strip()
            try:
                sector = int(sector_choice)
                if 0 <= sector <= 5:
                    self.test_sector = sector
                    await self.transition_to(OutputState.TEST_CLOCK_SECTOR)
                else:
                    print("Invalid sector number. Please enter a number between 0 and 5.")
            except ValueError:
                print("Invalid input. Please enter a number.")
                
        elif choice == '3':
            # Reset all servos to center
            await self.center_all_servos()
            
        elif choice == '4':
            # Set clock to custom position
            print("\nSet clock to custom position")
            print("Enter an angle between -150 and 150 degrees")
            angle_choice = input("\nEnter angle: ").strip()
            try:
                angle = float(angle_choice)
                if -150 <= angle <= 150:
                    await self.move_clock_to_angle(angle)
                else:
                    print("Invalid angle. Please enter a value between -150 and 150.")
            except ValueError:
                print("Invalid input. Please enter a number.")
            
        elif choice == '5':
            # Help
            self.display_help()
            
        elif choice == '6':
            print("\nExiting test mode...")
            os._exit(0)
            
        else:
            print("\nInvalid choice. Please try again.")
            
    def display_help(self):
        """Display help information about clock sectors"""
        print("\n=== Clock Sectors Explanation ===")
        print("The clock indicates time by pointing to one of 6 sectors around the circle.")
        print("Each sector represents a 4-hour period of the day:")
        print()
        print("Sector 0: 00:00-03:59 (-150° position)")
        print("         Midnight to early morning")
        print()
        print("Sector 1: 04:00-07:59 (-90° position)")
        print("         Early morning")
        print()
        print("Sector 2: 08:00-11:59 (-30° position)")
        print("         Late morning")
        print()
        print("Sector 3: 12:00-15:59 (+30° position)")
        print("         Early afternoon")
        print()
        print("Sector 4: 16:00-19:59 (+90° position)")
        print("         Late afternoon/early evening")
        print()
        print("Sector 5: 20:00-23:59 (+150° position) - HOME POSITION")
        print("         Evening/night")
        print()
        print("The time is calculated from sine/cosine values that represent")
        print("the cyclical nature of time throughout the day.")
        print("These values are converted to an angle between -180° and 180°,")
        print("which is then mapped to one of the six sectors.")
        print()
        print("In operation mode, the clock returns to sector 5 (HOME)")
        print("after displaying the calculated time sector.")
        
        # Only wait for input in test mode
        if self.mode == 'test':
            print("\nPress Enter to return to the menu...")
            input()

    async def center_all_servos_for_operation(self):
        """Center all servos before operation, with clock at sector 5 (150 degrees)"""
        print("\n=== Centering All Servos Before Operation ===")
        
        # Center cube servos (main controller)
        for servo_id in range(1, 6):
            command = {
                'type': 'servo',
                'controller': 'main',
                'servo_id': servo_id,
                'position': 0,  # 0 degrees is center
                'time_ms': 1000
            }
            response = self.output_node.process_command(command)
            if response['status'] == 'ok':
                print(f"✓ Centered cube servo {servo_id}")
                self.servo_positions[servo_id] = 0  # Track in degrees
            else:
                print(f"✗ Failed to center cube servo {servo_id}")
            await asyncio.sleep(0.1)
        
        # Position clock servo at sector 5 (150 degrees) for operation mode
        clock_command = {
            'type': 'servo',
            'controller': 'secondary',
            'servo_id': 1,
            'position': 150,  # 150 degrees (sector 5)
            'time_ms': 1000
        }
        response = self.output_node.process_command(clock_command)
        if response['status'] == 'ok':
            print(f"✓ Clock set to sector 5 (150°)")
            self.clock_current_angle = 150  # Track in degrees
        else:
            print(f"✗ Failed to set clock servo")
        
        print("=== All Servos Positioned ===")
        print("\nWaiting 2 seconds...")
        await asyncio.sleep(2)  # Wait 2 seconds after positioning
        print("Wait complete, proceeding...")

async def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Run Output Controller')
    parser.add_argument('--mode', choices=['operation', 'test'], default='operation', help='Controller mode (default: operation)')
    parser.add_argument('--port', type=int, default=8765, help='WebSocket server port (default: 8765)')
    parser.add_argument('--non-interactive', action='store_true', help='Run in non-interactive mode (no prompts)')
    parser.add_argument('--verbose', type=int, default=1, help='Verbosity level (0=minimal, 1=normal, 2=debug)')
    args = parser.parse_args()
    
    # Welcome message
    print("\n========== Reservoir Computer Output Controller ==========")
    print("  Venice Biennial Installation - Version 1.0")
    print("  Mode: {} | Port: {} | Verbosity: {}".format(
        args.mode, args.port, args.verbose))
    print("========================================================\n")
    
    # Check if we're running in an interactive terminal and not forced non-interactive
    interactive = sys.stdin.isatty() and not args.non_interactive
    
    mode = args.mode
    port = args.port
    verbose = args.verbose
    
    # Allow the user to choose the mode only in interactive mode
    if interactive:
        print("Select mode of operation:")
        print("1. WebSocket Server (Operation Mode) - Default")
        print("2. Direct Servo Control (Test Mode)")
        
        choice = input("Enter choice (1-2) or press Enter for default: ")
        if choice == "2":
            mode = "test"
            print("Selected Test Mode")
        else:
            mode = "operation"
            print("Selected Operation Mode")
    else:
        print(f"Running in non-interactive mode: {mode} mode")
    
    try:
        # Create and start output controller
        controller = OutputController(mode=mode, port=port, verbose=verbose)
        if verbose >= 1:
            print(f"Starting output controller in {mode} mode")
        await controller.start()
    except KeyboardInterrupt:
        print("\nCtrl+C detected, shutting down...")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Graceful shutdown
        if 'controller' in locals():
            await controller.stop()

if __name__ == "__main__":
    asyncio.run(main()) 