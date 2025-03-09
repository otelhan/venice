import asyncio
import websockets
import json
import numpy as np
from enum import Enum, auto
from src.networking.output_node import OutputNode
import argparse
import yaml
import os

class OutputState(Enum):
    IDLE = auto()
    PREDICT = auto()
    ROTATE_CUBES = auto()
    SHOW_TIME = auto()

class OutputController:
    def __init__(self, controller_name, port=8765):
        self.controller_name = controller_name
        self.port = port
        self.current_state = OutputState.IDLE
        self.output_node = OutputNode()
        self.received_data = None
        self.config = self._load_config()
        
        # Map each bin to a single servo
        self.servo_mapping = {
            1: 1,    # Bin 1 maps to servo 1
            2: 2,    # Bin 2 maps to servo 2
            3: 3,    # Bin 3 maps to servo 3
            4: 4,    # Bin 4 maps to servo 4
            5: 5     # Bin 5 maps to servo 5
        }
        
        # Track servo positions
        self.servo_positions = {1: 1500, 2: 1500, 3: 1500, 4: 1500, 5: 1500}  # Initialize at center

    def _load_config(self):
        """Load configuration from YAML"""
        config_path = os.path.join('config', 'controllers.yaml')
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return None

    async def start(self):
        """Start the output node and websocket server"""
        if not self.output_node.start():
            print("Failed to start output node")
            return

        print(f"\nStarting output controller: {self.controller_name}")
        print(f"Listening on port: {self.port}")
        
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
        if message.get('type') == 'data':
            movements = message.get('data', {}).get('movements', [])
            
            # Validate data
            if not isinstance(movements, list) or len(movements) != 30:
                return {"status": "error", "message": "Invalid data format"}
            
            if not all(20 <= x <= 127 for x in movements):
                return {"status": "error", "message": "Values must be between 20 and 127"}

            self.received_data = movements
            await self.transition_to(OutputState.PREDICT)
            return {"status": "ok", "message": "Data accepted"}

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
        print("\nCalculating servo positions...")
        
        # Create histogram bins
        bins = np.linspace(20, 127, 6)  # 5 bins between 20 and 127
        bin_indices = np.digitize(data, bins) - 1  # Get bin index for each value
        
        # Print initial positions
        await self.print_servo_positions()
        
        print("\nRotating servos based on bin averages:")
        for bin_num in range(5):
            # Get values in this bin
            bin_values = [val for val, idx in zip(data, bin_indices) if idx == bin_num]
            
            if bin_values:  # If bin has values
                # Calculate average of values in bin
                bin_avg = np.mean(bin_values)
                
                # Scale average from (20-127) to servo range (500-2500)
                position = int(((bin_avg - 20) / (127 - 20)) * (2500 - 500) + 500)
                
                # Get corresponding servo ID
                servo_id = self.servo_mapping[bin_num + 1]
                
                # Update stored position
                self.servo_positions[servo_id] = position
                
                print(f"\nBin {bin_num + 1}:")
                print(f"  Values: {bin_values}")
                print(f"  Average: {bin_avg:.1f}")
                print(f"  Servo {servo_id} position: {position} μs")
                
                # Send command to servo
                command = {
                    'type': 'servo',
                    'servo_id': servo_id,
                    'position': position,
                    'time_ms': 1000
                }
                response = self.output_node.handle_command(command)
                print(f"  Response: {response}")
                await asyncio.sleep(0.1)  # Small delay between commands
            else:
                print(f"\nBin {bin_num + 1}: No values")
        
        # Print final positions
        print("\nFinal Positions:")
        await self.print_servo_positions()

async def main():
    controller = OutputController("output")  # Fixed name
    await controller.start()

if __name__ == "__main__":
    print("\nStarting Output Controller")
    print("-------------------------")
    asyncio.run(main()) 