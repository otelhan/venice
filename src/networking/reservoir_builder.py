import asyncio
import pandas as pd
import os
import glob
import yaml
import json
import websockets
from datetime import datetime
from pathlib import Path
from src.networking.input_node import InputNode
import numpy as np
import traceback

class ReservoirModelBuilder:
    def __init__(self):
        self.config = self._load_config()
        self.data_dir = Path(__file__).parent.parent.parent / 'data'
        
        # Initialize connection state
        self.waiting_for_ack = False
        self.server = None  # WebSocket server
        self.listen_port = self.config['controllers']['builder'].get('listen_port', 8766)
        
        # Get destination from config
        if self.config and 'controllers' in self.config:
            self.builder_config = self.config['controllers'].get('builder', {})
            self.destination = self.builder_config.get('destination', 'res00')  # Default to res00
            print(f"\nBuilder config:", self.builder_config)
            print(f"Destination: {self.destination}")
        else:
            print("No builder config found!")
            
    def _load_config(self):
        """Load controller configurations"""
        config_path = Path(__file__).parent.parent.parent / 'config' / 'controllers.yaml'
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return None
            
    def list_available_data(self):
        """List all CSV files in the data directory"""
        csv_files = list(self.data_dir.glob('movement_vectors_*.csv'))
        if not csv_files:
            print("\nNo movement vector files found!")
            return []
            
        print("\nAvailable movement vector files:")
        for i, file in enumerate(csv_files, 1):
            print(f"{i}. {file.name}")
        return csv_files
        
    async def process_data_file(self, file_path):
        """Process data from CSV file and send to destination"""
        try:
            print(f"\nProcessing file: {file_path}")
            df = pd.read_csv(file_path)
            
            # Get second row (index 1)
            second_row = df.iloc[1]
            
            # Extract ROI values
            roi_values = [second_row[f'roi_1_m{i}'] for i in range(30)]
            
            # Create data packet
            data = {
                'type': 'movement_data',
                'timestamp': second_row['timestamp'] if 'timestamp' in second_row else str(datetime.now()),
                'data': {
                    'pot_values': roi_values,
                    't_sin': float(second_row['t_sin']),
                    't_cos': float(second_row['t_cos'])
                }
            }
            
            # Send to destination
            success = await self.send_to_destination(data)
            if success:
                print(f"\nListening for trainer signal on port {self.listen_port}")
                # Start listening server
                async with websockets.serve(
                    self.handle_connection, 
                    "0.0.0.0", 
                    self.listen_port
                ) as server:
                    # Wait for acknowledgment
                    while self.waiting_for_ack:
                        await asyncio.sleep(0.1)
                    print("Received acknowledgment, continuing...")
            else:
                print(f"Failed to send data to {self.destination}")
                
        except Exception as e:
            print(f"Error processing file: {e}")
            print("Available columns:", df.columns.tolist())

    @staticmethod
    def scale_movement_log(raw_movement, min_value, max_value):
        """
        Applies logarithmic scaling and converts movement to [20, 127] for DS1841 control.
        Guarantees output values are within [20, 127] range.
        """
        try:
            # Handle invalid input cases
            if max_value <= min_value:
                return 20
            if raw_movement <= min_value:
                return 20
            if raw_movement >= max_value:
                return 127
                
            # Apply logarithmic scaling
            log_scaled = np.log1p(raw_movement - min_value) / np.log1p(max_value - min_value)
            # log_scaled will be between 0 and 1
            
            # Scale to [20, 127] range
            scaled = int(round(20 + log_scaled * (127 - 20)))
            
            # Double-check bounds
            return max(20, min(127, scaled))
            
        except Exception as e:
            print(f"Error scaling movement value: {e}")
            return 20  # Return minimum value on error

    async def send_to_destination(self, data):
        """Send data to configured destination node"""
        try:
            dest_config = self.config['controllers'].get(self.destination)
            if not dest_config:
                print(f"Destination {self.destination} configuration not found!")
                return False

            uri = f"ws://{dest_config['ip']}:{dest_config.get('port', 8765)}"
            print(f"\nSending to {self.destination} at {uri}")

            async with websockets.connect(uri) as websocket:
                # Send the data
                await websocket.send(json.dumps(data))
                
                # Wait for response
                response = await websocket.recv()
                response_data = json.loads(response)
                
                if response_data.get('status') == 'success':
                    print(f"Data accepted by {self.destination}")
                    self.waiting_for_ack = True  # Set flag here after successful send
                    return True
                else:
                    print(f"{self.destination} rejected data: {response_data.get('message')}")
                    return False

        except Exception as e:
            print(f"Error sending to {self.destination}: {e}")
            return False

    async def handle_signal(self, websocket, signal):
        """Handle incoming ready signal from trainer"""
        try:
            signal_data = json.loads(signal)
            
            if signal_data.get('type') == 'ready_signal':
                if self.waiting_for_ack:  # Only accept signal if waiting for acknowledgment
                    print("Received ready signal from trainer")
                    self.waiting_for_ack = False  # Reset flag
                    await websocket.send(json.dumps({
                        'status': 'success',
                        'message': 'Signal acknowledged'
                    }))
                else:
                    print("Not waiting for acknowledgment")
                    await websocket.send(json.dumps({
                        'status': 'error',
                        'message': 'Not waiting for acknowledgment'
                    }))
            else:
                await websocket.send(json.dumps({
                    'status': 'error',
                    'message': 'Invalid signal type'
                }))

        except Exception as e:
            print(f"Error handling signal: {e}")
            await websocket.send(json.dumps({
                'status': 'error',
                'message': str(e)
            }))

    async def start(self):
        """Start by sending first row to destination, then listen for trainer"""
        try:
            # First send data to destination
            success = await self.process_data_file(self.current_file)
            if not success:
                print("Failed to send initial data")
                return

            # Then start listening for trainer signals
            print(f"\nListening for trainer signals on port {self.listen_port}")
            async with websockets.serve(
                self.handle_connection, 
                "0.0.0.0", 
                self.listen_port
            ) as server:
                await asyncio.Future()  # run forever

        except Exception as e:
            print(f"Error starting builder: {e}")

async def main():
    builder = ReservoirModelBuilder()
    
    while True:
        print("\nReservoir Model Builder")
        print("----------------------")
        print("1. Process movement data")
        print("2. Exit")
        
        choice = input("\nEnter choice: ").strip()
        
        if choice == '1':
            files = builder.list_available_data()
            if files:
                try:
                    file_num = int(input("\nSelect file number (or 0 to skip): "))
                    if file_num == 0:
                        continue
                    if 1 <= file_num <= len(files):
                        print(f"\nProcessing {files[file_num-1].name}")
                        print("(Will send data to configured destination:", builder.destination + ")")
                        await builder.process_data_file(files[file_num-1])
                except ValueError:
                    print("Invalid selection")
                    
        elif choice == '2':
            print("\nExiting...")
            break
            
        else:
            print("\nInvalid choice")

if __name__ == "__main__":
    asyncio.run(main()) 