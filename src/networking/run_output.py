import asyncio
import websockets
import json
import numpy as np
from enum import Enum, auto
from src.networking.output_node import OutputNode
import yaml
import os

class OutputState(Enum):
    IDLE = auto()
    PREDICT = auto()
    ROTATE_CUBES = auto()
    SHOW_TIME = auto()

class OutputController:
    def __init__(self):
        self.port = 8765
        self.current_state = OutputState.IDLE
        self.output_node = OutputNode()  # Will use /dev/ttyACM0 by default
        self.received_data = None
        
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

    async def start(self):
        """Start the output node and websocket server"""
        if not self.output_node.start():
            print("Failed to start output node")
            return

        print(f"\nStarting output controller")
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
        print(f"\nProcessing {len(data)} values into 5 bins")
        
        # Create histogram bins for 5 servos
        bins = np.linspace(20, 127, 6)  # Creates [20, 41.4, 62.8, 84.2, 105.6, 127]
        bin_indices = np.digitize(data, bins) - 1  # Get bin index for each value
        
        print("\nBin ranges:")
        for i in range(5):
            print(f"Bin {i+1}: {bins[i]:.1f} to {bins[i+1]:.1f}")
        
        print("\nRotating servos based on bin averages:")
        for bin_num in range(5):
            # Get values in this bin
            bin_values = [val for val, idx in zip(data, bin_indices) if idx == bin_num]
            servo_id = self.servo_mapping[bin_num + 1]
            
            if bin_values:
                # Calculate single average for this bin
                bin_avg = sum(bin_values) / len(bin_values)
                
                # Map the average to an angle:
                # bin_avg of 20 → -150 degrees
                # bin_avg of 127 → +150 degrees
                angle = ((bin_avg - 20) / (127 - 20)) * 300 - 150
                
                print(f"\nServo {servo_id}:")
                print(f"  Bin values: {bin_values}")
                print(f"  Average: {bin_avg:.1f}")
                print(f"  Target angle: {angle:.1f}°")
                
                # Send command to servo
                command = {
                    'type': 'servo',
                    'servo_id': servo_id,
                    'position': angle,
                    'time_ms': 1000  # 1 second movement
                }
                
                response = self.output_node.process_command(command)
                if response['status'] == 'ok':
                    print(f"  ✓ Moved to {angle:.1f}°")
                else:
                    print(f"  ✗ Failed: {response['message']}")
                
                await asyncio.sleep(0.1)  # Small delay between servos
            else:
                print(f"\nServo {servo_id}:")
                print("  No values in bin - skipping")
        
        return True

async def main():
    controller = OutputController()
    await controller.start()

if __name__ == "__main__":
    print("\nStarting Output Controller")
    print("-------------------------")
    asyncio.run(main())
