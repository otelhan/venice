import asyncio
import yaml
import random
import os
import time
import json
import websockets
from src.networking.input_node import InputNode

class ReservoirTester:
    def __init__(self):
        self.input_node = InputNode()
        self.config = self._load_config()
        self.packet_count = 0
        
    def _load_config(self):
        """Load controller configurations"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                 'config', 'controllers.yaml')
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return None
            
    def generate_movement_data(self):
        """Generate array of 30 random values between 20-127"""
        return [random.randint(20, 127) for _ in range(30)]
        
    async def send_to_controllers(self, controller_names):
        """Send movement data to specified controllers"""
        if not self.config or 'controllers' not in self.config:
            print("No controller configuration found!")
            return
            
        # Generate random movement data
        movements = self.generate_movement_data()
        self.packet_count += 1
        
        # Print movement data in a readable format
        print("\n=== Movement Packet #{} ===".format(self.packet_count))
        print("Values:")
        for i, value in enumerate(movements, 1):
            print(f"{i:2d}: {value:3d}", end='   ')
            if i % 5 == 0:  # New line every 5 values
                print()
        if len(movements) % 5 != 0:
            print()  # Add final newline if needed
        print("Average: {:.1f}".format(sum(movements)/len(movements)))
        print("Min: {}, Max: {}".format(min(movements), max(movements)))
        
        # Send to each specified controller
        for name in controller_names:
            if name in self.config['controllers']:
                controller = self.config['controllers'][name]
                print(f"\nSending to {name} ({controller['ip']})...")
                
                data_packet = {
                    'type': 'data',  # Add message type
                    'data': {  # Nest data under 'data' key
                        'movements': movements
                    },
                    'timestamp': time.time(),
                    'metadata': {
                        'source': 'reservoir_tester',
                        'type': 'test_movements',
                        'count': len(movements),
                        'packet_id': self.packet_count
                    }
                }
                
                try:
                    # Connect directly to controller's websocket
                    uri = f"ws://{controller['ip']}:8765"
                    async with websockets.connect(uri) as websocket:
                        await websocket.send(json.dumps(data_packet))
                        response = await websocket.recv()
                        print(f"Response: {response}")
                except Exception as e:
                    print(f"Error sending to {name}: {e}")
            else:
                print(f"Unknown controller: {name}")

async def main():
    tester = ReservoirTester()
    
    # Get controller names from command line
    print("\nAvailable controllers:")
    for name in tester.config['controllers']:
        print(f"- {name}")
    
    print("\nEnter controller names (comma-separated) or 'all':")
    input_names = input().strip()
    
    if input_names.lower() == 'all':
        controller_names = list(tester.config['controllers'].keys())
    else:
        controller_names = [name.strip() for name in input_names.split(',')]
    
    print(f"\nTargeting controllers: {', '.join(controller_names)}")
    print("\nControls:")
    print("- Press Enter to send random movements")
    print("- Type 'q' to quit")
    
    try:
        while True:
            # Get input with prompt
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("\nCommand (Enter/q): ").strip())
            
            if user_input.lower() == 'q':
                print("\nQuitting...")
                break
                
            await tester.send_to_controllers(controller_names)
    except KeyboardInterrupt:
        print("\nTest ended by user")

if __name__ == "__main__":
    asyncio.run(main()) 