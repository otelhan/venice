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
        
        # Map each bin to a single servo
        self.servo_mapping = {
            1: 1,    # Bin 1 maps to servo 1
            2: 2,    # Bin 2 maps to servo 2
            3: 3,    # Bin 3 maps to servo 3
            4: 4,    # Bin 4 maps to servo 4
            5: 5     # Bin 5 maps to servo 5
        }
        
        # Track servo positions
        self.servo_positions = {1: 1500, 2: 1500, 3: 1500, 4: 1500, 5: 1500}
        
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
        """Center all servos to their neutral positions"""
        print("\n=== Centering All Servos ===")
        
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
                self.servo_positions[servo_id] = 0
            else:
                print(f"✗ Failed to center cube servo {servo_id}")
            await asyncio.sleep(0.1)
        
        # Center clock servo (secondary controller)
        clock_command = {
            'type': 'servo',
            'controller': 'secondary',
            'servo_id': 1,
            'position': 0,
            'time_ms': 1000
        }
        response = self.output_node.process_command(clock_command)
        if response['status'] == 'ok':
            print(f"✓ Centered clock servo")
            self.clock_current_angle = 0
        else:
            print(f"✗ Failed to center clock servo")
        
        print("=== All Servos Centered ===")
        await asyncio.sleep(3)  # Wait 3 seconds after centering

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
        
        if msg_type == 'data':
            movements = message.get('data', {}).get('movements', [])
            
            # Validate data
            if not isinstance(movements, list) or len(movements) != 30:
                return {"status": "error", "message": "Invalid data format"}
            
            if not all(20 <= x <= 127 for x in movements):
                return {"status": "error", "message": "Values must be between 20 and 127"}

            self.received_data = movements
            await self.transition_to(OutputState.PREDICT)
            return {"status": "ok", "message": "Data accepted"}
            
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
            await self.move_clock()
            await self.transition_to(OutputState.IDLE)
            
        elif self.current_state == OutputState.TEST_MODE:
            if self.test_data:
                # Extract values from test data
                data = self.test_data['data']
                t_sin = data['t_sin']
                t_cos = data['t_cos']
                pot_values = data['pot_values']
                
                # Calculate clock angle
                target_angle = self.calculate_clock_angle(t_sin, t_cos)
                print(f"\nTest Mode - Moving clock to angle: {target_angle:.2f}°")
                
                # Move clock to calculated position
                clock_command = {
                    'type': 'servo',
                    'controller': 'secondary',
                    'servo_id': 1,
                    'position': target_angle,
                    'time_ms': 1000
                }
                
                response = self.output_node.process_command(clock_command)
                if response['status'] == 'ok':
                    print(f"✓ Clock moved to {target_angle:.2f}°")
                else:
                    print("✗ Failed to move clock servo")
                
                # Process pot values
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
        for servo_id, position in self.servo_positions.items():
            # Convert position to degrees (500-2500 → 0-180)
            degrees = (position - 500) * 180 / 2000
            print(f"Servo {servo_id}: {position} μs ({degrees:.1f}°)")
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
                    # Update tracked position
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

    async def move_clock(self):
        """Move the clock servo in its sequence"""
        print("\n=== Moving Clock Servo ===")
        
        # Load servo config for clock
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config', 'controllers.yaml')
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                servo_config = config.get('servo_config', {})
                secondary_controller = servo_config.get('controllers', {}).get('secondary', {})
                clock_servo = secondary_controller.get('servos', {}).get('1', {})
        except Exception as e:
            print(f"Warning: Could not load clock servo config: {e}")
            clock_servo = {}
        
        # Update clock angle
        old_angle = self.clock_current_angle
        self.clock_current_angle += 60 * self.clock_direction
        
        # Get configured limits
        min_angle = clock_servo.get('min_angle', -150.0)
        max_angle = clock_servo.get('max_angle', 150.0)
        
        # Check bounds and reverse direction if needed
        if abs(self.clock_current_angle) >= max_angle:
            self.clock_direction *= -1  # Reverse direction
            self.clock_current_angle = max_angle if self.clock_current_angle > 0 else min_angle
            print(f"Hit limit ({max_angle}°), reversing direction. New direction: {self.clock_direction}")
        
        print(f"Moving from {old_angle:.1f}° → {self.clock_current_angle:.1f}°")
        print(f"Servo limits: {min_angle}° to {max_angle}°")
        
        # Send command to clock servo
        clock_command = {
            'type': 'servo',
            'controller': 'secondary',
            'servo_id': 1,
            'position': self.clock_current_angle,
            'time_ms': 1000
        }
        
        response = self.output_node.process_command(clock_command)
        if response['status'] == 'ok':
            print(f"✓ Clock moved to {self.clock_current_angle:.1f}°")
        else:
            print("✗ Failed to move clock servo")
        
        await asyncio.sleep(1.1)
        print("=== Clock Move Complete ===")
        return True

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
    finally:
        if controller.output_node:
            controller.output_node.stop()

if __name__ == "__main__":
    print("\nStarting Output Controller")
    print("-------------------------")
    asyncio.run(main()) 