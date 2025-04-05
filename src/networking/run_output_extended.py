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

class OutputState(Enum):
    IDLE = auto()
    PREDICT = auto()
    ROTATE_CUBES = auto()
    SHOW_TIME = auto()
    TEST_MODE = auto()

class OutputController:
    def __init__(self, mode='operation'):
        self.port = 8765
        self.current_state = OutputState.IDLE
        self.output_node = OutputNode()
        self.received_data = None
        self.clock_direction = 1  # 1 for increasing angle, -1 for decreasing
        self.clock_current_angle = 0
        self.mode = mode
        
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
        """Start the output node and websocket server"""
        if not self.output_node.start():
            print("Failed to start output node")
            return

        print(f"\nStarting output controller in {self.mode} mode")
        print(f"Listening on port: {self.port}")
        
        # Center all servos at startup
        await self.center_all_servos()
        
        # If in test mode, transition to test mode immediately
        if self.mode == 'test':
            await self.transition_to(OutputState.TEST_MODE)
            return
        
        # Otherwise start websocket server for operation mode
        async with websockets.serve(
            self._handle_connection, 
            "0.0.0.0", 
            self.port,
            max_size=None
        ) as server:
            await asyncio.Future()  # run forever

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
        if self.current_state == OutputState.IDLE:
            print("Waiting for data...")

        elif self.current_state == OutputState.PREDICT:
            print("Predicting (placeholder - waiting 3 seconds)")
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
            
            # Send acknowledgment to video_input after clock movement is complete
            if self.mode == 'operation' and timestamp:
                success = await self.send_acknowledgement(timestamp)
                if success:
                    print("Acknowledgment sent to video_input")
                else:
                    print("Failed to send acknowledgment to video_input")
            
            await self.transition_to(OutputState.IDLE)
            
        elif self.current_state == OutputState.TEST_MODE:
            if self.test_data:
                # Extract values from test data
                data = self.test_data['data']
                pot_values = data['pot_values']
                
                # First move clock using new method
                await self.move_clock()
                
                # Then process pot values
                await self.rotate_cubes(pot_values)
                
                # Return to idle
                await self.transition_to(OutputState.IDLE)
            else:
                print("No test data available")
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
        print(f"Mapped to sector {sector + 1}/6 ({sector * 4}-{(sector + 1) * 4} hours)")
        print(f"Current angle: {self.clock_current_angle:.1f}°")
        print(f"Target angle: {target_angle:.1f}°")
        
        # First return to center
        center_command = {
            'type': 'servo',
            'controller': 'secondary',
            'servo_id': 1,
            'position': 0,  # 0 degrees is center
            'time_ms': 1000
        }
        
        print("Moving to center position...")
        response = self.output_node.process_command(center_command)
        if response['status'] == 'ok':
            print("✓ Clock centered")
            self.clock_current_angle = 0
            await asyncio.sleep(3)  # Wait 3 seconds at center
        else:
            print("✗ Failed to center clock servo")
            return False
        
        # Perform one full rotation
        print("\nPerforming full rotation...")
        rotation_angles = [-150, -90, -30, 30, 90, 150, -150]  # Complete cycle
        for angle in rotation_angles:
            rotation_command = {
                'type': 'servo',
                'controller': 'secondary',
                'servo_id': 1,
                'position': angle,
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
        
        # Finally move to target position
        print(f"\nMoving to final position in sector {sector + 1}...")
        clock_command = {
            'type': 'servo',
            'controller': 'secondary',
            'servo_id': 1,
            'position': target_angle,
            'time_ms': 1000
        }
        
        response = self.output_node.process_command(clock_command)
        if response['status'] == 'ok':
            print(f"✓ Clock moved to sector {sector + 1} ({target_angle:.1f}°)")
            self.clock_current_angle = target_angle
        else:
            print("✗ Failed to move clock servo")
            return False
        
        await asyncio.sleep(1.1)
        print("=== Clock Move Complete ===")
        return True

    async def send_acknowledgement(self, timestamp):
        """Send acknowledgement back to video_input"""
        try:
            # Get video_input configuration
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                    'config', 'controllers.yaml')
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            video_input_config = config.get('video_input', {})
            if not video_input_config:
                print("No video_input configuration found")
                return False
            
            # Connect to video_input's IP and listen_port
            video_ip = video_input_config.get('ip', '127.0.0.1')
            video_listen_port = video_input_config.get('listen_port', 8777)
            
            uri = f"ws://{video_ip}:{video_listen_port}"
            print(f"\nSending acknowledgment to video_input:")
            print(f"URI: {uri}")
            
            async with websockets.connect(uri) as websocket:
                print("Connected to video_input")
                ack = {
                    'type': 'ack',
                    'timestamp': timestamp,
                    'status': 'success',
                    'message': 'Clock movement complete'
                }
                await websocket.send(json.dumps(ack))
                print("Acknowledgement sent to video_input")
                return True
            
        except Exception as e:
            print(f"Error sending acknowledgement: {e}")
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

async def main():
    # Print welcome message
    print("\n=== Output Controller ===")
    print("1. Operation Mode (WebSocket Server)")
    print("2. Test Mode (Direct Servo Control)")
    
    while True:
        choice = input("\nSelect mode (1/2): ").strip()
        if choice in ['1', '2']:
            break
        print("Invalid choice. Please enter 1 or 2.")
    
    # Create controller with selected mode
    mode = 'operation' if choice == '1' else 'test'
    controller = OutputController(mode)
    
    try:
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