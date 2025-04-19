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

class OutputState(Enum):
    IDLE = auto()
    PREDICT = auto()
    ROTATE_CUBES = auto()
    SHOW_TIME = auto()
    TEST_MODE = auto()
    TEST_CLOCK_SECTOR = auto()  # New state for testing specific clock sectors
    START_POSITION = auto()  # New state for initial startup position

class OutputController:
    def __init__(self, mode='operation'):
        self.port = 8765
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
            
            # Increase the delay between servo commands to prevent communication issues
            await asyncio.sleep(0.5)
        
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
        """Start the output node and websocket server"""
        # Simple USB reset - try to cycle the USB connections
        print("\n=== Attempting USB device reset ===")
        try:
            import serial
            
            # Try to reset the USB connections by opening and closing them
            usb_devices = ["/dev/ttyACM0", "/dev/ttyACM1"]
            for device in usb_devices:
                if os.path.exists(device):
                    print(f"Resetting {device}...")
                    try:
                        ser = serial.Serial(device, 115200)
                        ser.close()
                        print(f"Successfully reset {device}")
                    except Exception as e:
                        print(f"Could not reset {device}: {e}")
            
            # Wait for devices to stabilize
            print("Waiting for USB devices to stabilize...")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"Error during USB reset: {e}")
            print("Continuing anyway...")
        
        # Add retry logic for connecting to servo boards
        max_retries = 5
        retry_delay = 3  # seconds
        
        for attempt in range(max_retries):
            print(f"\nAttempt {attempt+1}/{max_retries} to connect to servo boards...")
            
            if self.output_node.start():
                print("✓ Successfully connected to servo boards")
                break
            else:
                print(f"× Failed to start output node on attempt {attempt+1}")
                
                if attempt < max_retries - 1:
                    print(f"Waiting {retry_delay} seconds before retrying...")
                    await asyncio.sleep(retry_delay)
                else:
                    print("All connection attempts failed. Cannot proceed.")
                    return
        
        print(f"\nStarting output controller in {self.mode} mode")
        print(f"Listening on port: {self.port}")
        
        # Center all servos at startup
        await self.center_all_servos()
        
        # Start in START_POSITION state
        await self.transition_to(OutputState.START_POSITION)

    async def _handle_connection(self, websocket):
        """Handle incoming websocket connections"""
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    response = await self.handle_message(data)
                    await websocket.send(json.dumps(response))
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "status": "error",
                        "message": "Invalid JSON"
                    }))
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")

    async def handle_message(self, message):
        """Handle incoming messages"""
        msg_type = message.get('type', '')
        
        if msg_type == 'movement_data':
            # Extract data from the message
            timestamp = message.get('timestamp')
            data = message.get('data', {})
            movements = data.get('pot_values', [])
            t_sin = data.get('t_sin')
            t_cos = data.get('t_cos')
            
            # Validate data
            if not isinstance(movements, list) or len(movements) != 30:
                return {"status": "error", "message": "Invalid data format"}
            
            if not all(20 <= x <= 127 for x in movements):
                return {"status": "error", "message": "Values must be between 20 and 127"}
            
            if t_sin is None or t_cos is None:
                return {"status": "error", "message": "Missing time reference data"}

            print(f"\nReceived movement data at {timestamp}")
            print(f"Time reference - sin: {t_sin:.3f}, cos: {t_cos:.3f}")
            
            # Store the data and time reference
            self.received_data = movements
            
            # Store the entire message for later acknowledgment
            self.test_data = message
            
            # Save to CSV
            if self.mode == 'operation':
                save_success = self.save_to_csv(message)
                if save_success:
                    print("Data saved to CSV file")
                else:
                    print("Failed to save data to CSV file")
            
            # Process the data through state machine
            await self.transition_to(OutputState.PREDICT)
            
            # Return success response (not the final acknowledgment)
            return {
                "status": "success",
                "message": "Data received, processing started"
            }
            
        elif msg_type == 'test':
            print("\nReceived test command")
            self.load_test_data()
            await self.transition_to(OutputState.TEST_MODE)
            return {"status": "ok", "message": "Test mode activated"}

        return {"status": "error", "message": "Unknown message type"}

    async def transition_to(self, new_state):
        """Transition to a new state"""
        print(f"Transitioning from {self.current_state.name} to {new_state.name}")
        self.current_state = new_state
        await self.handle_current_state()

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
                    self._handle_connection, 
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
            print("\n=== Sending Acknowledgment to Video Input ===")
            
            # Get video_input configuration
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                    'config', 'controllers.yaml')
            print(f"Loading config from: {config_path}")
            
            try:
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                print("Config loaded successfully")
            except Exception as e:
                print(f"Failed to load config: {e}")
                return False
            
            # Print entire video_input config for debugging
            video_input_config = config.get('video_input', {})
            print(f"\nVideo input config: {video_input_config}")
            
            if not video_input_config:
                print("No video_input configuration found in config file")
                return False
            
            # Connect to video_input's IP and listen_port
            video_ip = video_input_config.get('ip')
            if not video_ip:
                print("No IP address defined for video_input in config")
                return False
                
            video_listen_port = video_input_config.get('listen_port')
            if not video_listen_port:
                print("No listen_port defined for video_input in config")
                video_listen_port = 8777  # Default port
            
            uri = f"ws://{video_ip}:{video_listen_port}"
            print(f"Acknowledgment URI: {uri}")
            
            # Try to ping the target IP first to verify connectivity
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
                    print(f"\nAttempt {attempt+1}/{max_retries} to send acknowledgment")
                    
                    # Use more lenient timeout settings
                    async with asyncio.timeout(5):
                        async with websockets.connect(
                            uri,
                            ping_interval=None,
                            ping_timeout=None,
                            close_timeout=2.0
                        ) as websocket:
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
                            print(f"Sending ack: {ack_json}")
                            
                            # Send the acknowledgment
                            await websocket.send(ack_json)
                            print("✓ Acknowledgment JSON sent successfully")
                            
                            # Wait briefly for any response (optional but helpful for debugging)
                            try:
                                response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                                print(f"Received response: {response}")
                            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                                # No response is expected, so this is fine
                                print("No response received (this is normal)")
                                
                            # Keep connection open a little longer to ensure message is received
                            await asyncio.sleep(1)
                            print("Acknowledgment completed successfully")
                            return True
                            
                except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed) as e:
                    error_type = "Timeout" if isinstance(e, asyncio.TimeoutError) else "Connection closed"
                    print(f"× {error_type} on attempt {attempt+1}: {str(e) or 'No details'}")
                    
                    if attempt < max_retries - 1:
                        print(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                    else:
                        print("All retry attempts failed")
                        
                except Exception as e:
                    print(f"× Unexpected error on attempt {attempt+1}: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    if attempt < max_retries - 1:
                        print(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                    else:
                        print("All retry attempts failed")
            
            print("=== Failed to send acknowledgment ===")
            return False
            
        except Exception as e:
            print(f"× Error in acknowledgment process: {e}")
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
        """Get path for CSV file with session uniqueness to prevent overwriting"""
        # Get current Venice time
        venice_time = self.get_venice_time()
        date_str = venice_time.strftime('%Y%m%d')
        
        # Create a session ID based on startup timestamp to ensure uniqueness
        if not hasattr(self, 'session_id'):
            # Generate a unique session ID using timestamp and random number
            import random
            import time
            random.seed(time.time())
            self.session_id = f"{int(time.time())}_{random.randint(1000, 9999)}"
            print(f"Generated unique session ID: {self.session_id}")
        
        # Include both date and session ID in filename to prevent overwrites
        filename = f"processed_movement_{date_str}_session_{self.session_id}.csv"
        
        # Return full path 
        return os.path.join(self.data_dir, filename)
        
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
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Output Controller for Reservoir Computer')
    parser.add_argument('--mode', '-m', type=str, choices=['operation', 'test'], 
                       default='operation', help='Mode to run in (default: operation)')
    parser.add_argument('--port', '-p', type=int, default=8765,
                       help='Port to listen on (default: 8765)')
    parser.add_argument('--non-interactive', '-n', action='store_true',
                       help='Run in non-interactive mode (no prompts)')
    args = parser.parse_args()
    
    # Use command line arguments
    mode = args.mode
    non_interactive = args.non_interactive
    
    # Print welcome message with mode information
    print("\n=== Output Controller ===")
    print(f"Starting in {mode.upper()} mode")
    
    # Only show mode selection if in interactive terminal and not explicitly set to non-interactive
    if os.isatty(0) and not non_interactive and not os.environ.get('NON_INTERACTIVE'):
        print("\n1. Operation Mode (WebSocket Server)")
        print("2. Test Mode (Direct Servo Control)")
        print(f"Default: {mode.upper()} mode")
        
        choice = input("\nSelect mode (1/2) or press Enter for default: ").strip()
        if choice == '1':
            mode = 'operation'
        elif choice == '2':
            mode = 'test'
        # Empty input uses the default from command line args
    else:
        print("Running in non-interactive mode")
    
    # Create controller with selected mode
    controller = OutputController(mode)
    
    try:
        # Start controller (this will center servos after connection is established)
        await controller.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"\nError occurred: {e}")
    finally:
        controller.stop()  # Use the new stop method

if __name__ == "__main__":
    print("\nStarting Output Controller")
    print("-------------------------")
    asyncio.run(main()) 