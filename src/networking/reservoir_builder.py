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
from enum import Enum

class BuilderState(Enum):
    IDLE = "IDLE"
    SENDING_DATA = "SENDING_DATA"

class ReservoirModelBuilder:
    def __init__(self):
        self.config = self._load_config()
        self.data_dir = Path(__file__).parent.parent.parent / 'data'
        
        # Initialize connection state
        self.waiting_for_ack = False
        self.server = None
        self.listen_port = self.config['controllers']['builder'].get('listen_port', 8766)
        self.current_state = BuilderState.IDLE
        
        # Get destination from config
        if self.config and 'controllers' in self.config:
            self.builder_config = self.config['controllers'].get('builder', {})
            self.destination = self.builder_config.get('destination', 'res00')
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
        
    async def process_data_file(self, file):
        """Process a data file"""
        try:
            print(f"\nProcessing {file.name}")
            self.current_file = file
            
            # Read first row
            df = pd.read_csv(file)
            if df.empty:
                print("File is empty")
                return False
                
            # Send first row to destination
            self.transition_to(BuilderState.SENDING_DATA)
            first_row = df.iloc[0]
            
            # Extract ROI values and create data packet
            roi_values = [first_row[f'roi_1_m{i}'] for i in range(30)]
            data = {
                'type': 'movement_data',
                'timestamp': first_row['timestamp'] if 'timestamp' in first_row else str(datetime.now()),
                'data': {
                    'pot_values': roi_values,
                    't_sin': float(first_row['t_sin']),
                    't_cos': float(first_row['t_cos'])
                }
            }
            
            # Send to destination
            success = await self.send_to_destination(data)
            
            # Always transition to IDLE to wait for acknowledgement
            self.transition_to(BuilderState.IDLE)
            
            if success:
                print("First row sent successfully")
                print("Waiting for acknowledgement...")
                return True
            else:
                print("Failed to send first row")
                return False
                
        except Exception as e:
            print(f"Error processing file: {e}")
            print("Available columns:", df.columns.tolist())
            self.transition_to(BuilderState.IDLE)
            return False

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
        """Send data to destination controller"""
        max_retries = 3
        retry_delay = 2  # seconds between retries
        
        try:
            target = self.config['controllers'].get(self.destination)
            if not target:
                print(f"Unknown destination: {self.destination}")
                return False

            uri = f"ws://{target['ip']}:{target.get('port', 8765)}"
            
            # Print the data being sent
            print("\nSending data packet:")
            print(json.dumps(data, indent=2))
            
            # Only try once and return result - don't retry
            try:
                print(f"\nSending to {self.destination} at {uri}")
                async with websockets.connect(uri) as websocket:
                    await websocket.send(json.dumps(data))
                    response = await websocket.recv()
                    response_data = json.loads(response)
                    
                    if response_data.get('status') == 'success':
                        print(f"Data accepted by {self.destination}")
                        return True
                    else:
                        print(f"Error from {self.destination}:", response_data.get('message'))
                        return False
                        
            except Exception as e:
                print(f"Error sending data: {e}")
                return False
                    
        except Exception as e:
            print(f"Error sending to {self.destination}: {e}")
            return False

    async def handle_connection(self, websocket):
        """Handle incoming websocket connections"""
        try:
            # Only accept connections when in IDLE state
            if self.current_state != BuilderState.IDLE:
                print(f"Received connection in wrong state: {self.current_state}")
                await websocket.send(json.dumps({
                    'status': 'error',
                    'message': 'Not ready for acknowledgement'
                }))
                return
                
            # Wait for acknowledgement from trainer
            message = await websocket.recv()
            data = json.loads(message)
            
            print(f"\nReceived from trainer: {data}")
            
            if data.get('type') == 'ack':
                # Process acknowledgement and send next row
                await self.send_next_row()
                await websocket.send(json.dumps({'status': 'ok'}))
            else:
                await websocket.send(json.dumps({
                    'status': 'error',
                    'message': 'Expected acknowledgement'
                }))
                
        except Exception as e:
            print(f"Error handling connection: {e}")
            try:
                await websocket.send(json.dumps({
                    'status': 'error',
                    'message': str(e)
                }))
            except:
                pass

    async def send_next_row(self):
        """Send next row after acknowledgement"""
        try:
            if not self.current_file:
                print("No file being processed")
                return False

            # Read current file
            df = pd.read_csv(self.current_file)
            
            # Get current row index from state
            current_index = getattr(self, 'current_row_index', 0)
            next_index = current_index + 1

            if next_index >= len(df):
                print("Reached end of file")
                return False

            # Get next row
            row = df.iloc[next_index]
            
            # Extract ROI values and create data packet
            roi_values = [row[f'roi_1_m{i}'] for i in range(30)]
            data = {
                'type': 'movement_data',
                'timestamp': row['timestamp'] if 'timestamp' in row else str(datetime.now()),
                'data': {
                    'pot_values': roi_values,
                    't_sin': float(row['t_sin']),
                    't_cos': float(row['t_cos'])
                }
            }

            print("\nSending next row...")
            # Switch to sending state
            self.transition_to(BuilderState.SENDING_DATA)
            
            # Send to destination
            success = await self.send_to_destination(data)
            
            print("Switching to IDLE to wait for acknowledgement...")
            # Always return to IDLE after sending
            self.transition_to(BuilderState.IDLE)
            
            if success:
                print(f"Sent row {next_index} of {len(df)-1}")
                self.current_row_index = next_index  # Update index after successful send
                return True
            else:
                print("Failed to send next row")
                return False

        except Exception as e:
            print(f"Error processing next row: {e}")
            self.transition_to(BuilderState.IDLE)
            return False

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
            
            # Create websocket server that keeps running
            async with websockets.serve(
                self.handle_connection, 
                "0.0.0.0",  # Listen on all interfaces
                self.listen_port,
                ping_interval=None  # Disable ping to prevent timeouts
            ) as server:
                print(f"Server started on port {self.listen_port}, waiting for acknowledgements...")
                # Keep the server running until all data is sent
                while True:
                    if self.current_state == BuilderState.IDLE:
                        if hasattr(self, 'current_row_index'):
                            df = pd.read_csv(self.current_file)
                            if self.current_row_index >= len(df) - 1:
                                print("All data sent, stopping server")
                                break
                    await asyncio.sleep(0.1)

        except Exception as e:
            print(f"Error starting builder: {e}")
            print(f"Exception details: {type(e).__name__}")  # Add more error details
            import traceback
            traceback.print_exc()

    def transition_to(self, new_state):
        """Transition to a new state"""
        print(f"\nTransitioning from {self.current_state.name} to {new_state.name}")
        self.current_state = new_state

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