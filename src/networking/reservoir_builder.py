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
            # Convert string path to Path object if needed
            file_path = Path(file) if isinstance(file, str) else file
            print(f"\nProcessing {file_path.name}")
            self.current_file = file_path
            
            # Read file and check if we have enough data points (4 * 30 seconds = 2 minutes)
            df = pd.read_csv(file_path)
            if len(df) < 4:
                print(f"Not enough data points yet (have {len(df)}, need at least 4)")
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
            
            # Store the timestamp we're processing to avoid duplicates
            self.last_processed_timestamp = first_row['timestamp'] if 'timestamp' in first_row else None
            
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
            if 'df' in locals():
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
        try:
            # Get destination config
            dest_config = self.config['controllers'].get(self.destination)
            if not dest_config:
                print(f"No configuration found for destination: {self.destination}")
                return False

            # Connect to destination's specific IP
            uri = f"ws://{dest_config['ip']}:{dest_config.get('listen_port', 8765)}"
            print(f"\nConnecting to {self.destination}:")
            print(f"URI: {uri}")
            
            async with websockets.connect(uri) as websocket:
                print(f"Connected to {self.destination}")
                await websocket.send(json.dumps(data))
                print(f"Data sent to {self.destination}")
                return True

        except Exception as e:
            print(f"Error sending to destination: {e}")
            return False

    async def handle_connection(self, websocket):
        """Handle incoming WebSocket connections"""
        try:
            async for message in websocket:
                data = json.loads(message)
                if data.get('type') == 'ack':
                    print("\nReceived acknowledgement")
                    print(json.dumps(data, indent=2))
                    
                    # Send next row after acknowledgement
                    print("\nSending next row...")
                    await self.send_next_row()
                    
                    # Don't close connection - keep waiting for next ack
                    
        except websockets.exceptions.ConnectionClosed:
            print("\nAcknowledgement connection closed - waiting for new connection")
            # Don't exit - let the server keep running
            
        except Exception as e:
            print(f"Error handling acknowledgement: {e}")
            # Keep server running

    async def send_next_row(self):
        """Send next row after acknowledgement"""
        try:
            if not self.current_file:
                print("No file being processed")
                return False

            # Re-read the file to get any new rows
            df = pd.read_csv(self.current_file)
            
            # Find the next unprocessed row
            if hasattr(self, 'last_processed_timestamp') and self.last_processed_timestamp:
                # Find the index of the last processed row
                processed_idx = df[df['timestamp'] == self.last_processed_timestamp].index[0]
                next_index = processed_idx + 1
            else:
                next_index = 0

            if next_index >= len(df):
                print("Reached end of current data, waiting for more...")
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
                # Update the last processed timestamp
                self.last_processed_timestamp = row['timestamp'] if 'timestamp' in row else None
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
            # Get latest CSV file
            csv_files = self.list_available_data()
            if not csv_files:
                print("No data files found")
                return

            # Use the most recent file
            self.current_file = max(csv_files, key=lambda p: p.stat().st_mtime)
            print(f"\nUsing data file: {self.current_file}")

            # First send data to destination
            success = await self.process_data_file(self.current_file)
            if not success:
                print("Failed to send initial data")
                return

            # Then start listening for trainer signals on all interfaces
            print(f"\nStarting WebSocket server...")
            print(f"Host: 0.0.0.0 (all interfaces)")
            print(f"Port: {self.listen_port}")
            
            async with websockets.serve(
                self.handle_connection, 
                "0.0.0.0",  # Listen on all interfaces
                self.listen_port,
                ping_interval=None
            ) as server:
                print(f"Server started successfully")
                print(f"Current state: {self.current_state.name}")
                print("Waiting for acknowledgement before sending next row...")

                # Keep the server running and check for new data
                while True:
                    if self.current_state == BuilderState.IDLE:
                        # Re-read the file to check for new rows
                        df = pd.read_csv(self.current_file)
                        if hasattr(self, 'last_processed_timestamp'):
                            processed_idx = df[df['timestamp'] == self.last_processed_timestamp].index[0]
                            if processed_idx >= len(df) - 1:
                                # We've processed all rows, wait for more data
                                await asyncio.sleep(5)  # Wait 5 seconds before checking again
                                continue
                    await asyncio.sleep(0.1)

        except Exception as e:
            print(f"Error in start: {e}")
            return False

    def transition_to(self, new_state):
        """Transition to a new state"""
        print(f"\nTransitioning from {self.current_state.name} to {new_state.name}")
        self.current_state = new_state

    async def run(self):
        """Main run loop - automatically start processing data"""
        print("\nReservoir Model Builder")
        print("----------------------")
        
        # Automatically start processing data
        await self.start()

async def main():
    """Start the builder automatically"""
    builder = ReservoirModelBuilder()
    await builder.run()

if __name__ == "__main__":
    asyncio.run(main()) 