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
        self.config = self._load_config()
        # Initialize input node with config
        self.input_node = InputNode()
        self.input_node.config = self.config
        self.input_node.controllers = self.config.get('controllers', {})
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
        # Generate random movement data first
        self.movement_buffer = self.generate_movement_data()
        self.input_node.movement_buffer = self.movement_buffer
        
        print("\nGenerated movement data:")
        print(self.movement_buffer)
        
        for controller in controller_names:
            try:
                if controller not in self.config['controllers']:
                    print(f"\nController {controller} not found in config!")
                    print(f"Available controllers: {list(self.config['controllers'].keys())}")
                    continue
                    
                print(f"\nSending to {controller}...")
                print(f"IP: {self.config['controllers'][controller]['ip']}")
                response = await self.input_node.send_movement_data(controller)
                
                if response.get('status') == 'rejected':
                    print(f"Message rejected by {controller}: {response.get('message')}")
                    continue
                elif response.get('status') == 'error':
                    print(f"Error from {controller}: {response.get('message')}")
                    continue
                    
                print(f"Successfully sent to {controller}")
                
            except Exception as e:
                print(f"Error sending to {controller}: {e}")
                continue

async def main():
    tester = ReservoirTester()
    
    # Get controller names from command line
    print("\nAvailable controllers:")
    for name, details in tester.config['controllers'].items():
        print(f"- {name} ({details['description']}) at {details['ip']}")
    
    print("\nEnter controller names (comma-separated), 'output' for output node, or 'all':")
    input_names = input().strip()
    
    if input_names.lower() == 'all':
        controller_names = list(tester.config['controllers'].keys())
    elif input_names.lower() == 'output':
        controller_names = ['output']
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