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
        """Rotate the cubes based on the received data"""
        print(f"Rotating cubes with data: {data}")
        
        # Convert data to servo positions
        values = data['values']
        print(f"Values: {values}")
        
        # Calculate average
        avg = sum(values) / len(values)
        print(f"Average: {avg}")
        
        # Map average to servo position
        # Example: map 0-100 to 500-2500 microseconds
        position = avg  # You might want to scale this appropriately
        
        # Send command to servo
        command = {
            'type': 'servo',
            'servo_id': 1,  # Using first servo
            'position': position,  # Now in degrees (-150 to +150)
            'time_ms': 1000  # Take 1 second to move
        }
        
        print(f"Servo 1 position: {position} μs")
        
        # Send command to output node
        response = self.output_node.process_command(command)  # Changed from handle_command to process_command
        
        if response['status'] != 'ok':
            print(f"Error rotating cubes: {response['message']}")
            return False
            
        return True

async def main():
    controller = OutputController()
    await controller.start()

if __name__ == "__main__":
    print("\nStarting Output Controller")
    print("-------------------------")
    asyncio.run(main())
