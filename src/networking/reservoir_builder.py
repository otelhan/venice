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
        self.input_node = InputNode()
        self.config = self._load_config()
        self.data_dir = Path(__file__).parent.parent.parent / 'data'
        self.output_dir = self.data_dir / 'reservoir_output'
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize connection state
        self.connected_reservoir = None
        self.is_listening = False
        self.received_data = []
        self.waiting_for_ack = False  # Track if waiting for acknowledgment
        self.server = None  # WebSocket server
        self.send_port = 8765  # Standard port for sending to res00
        self.listen_port = self.config['controllers']['builder'].get('listen_port', 8766)
        
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
        
    def select_reservoir(self):
        """Select a reservoir node to connect to"""
        print("\nAvailable reservoir nodes:")
        reservoirs = [name for name, details in self.config['controllers'].items() 
                     if name.startswith('res')]
                     
        for i, name in enumerate(reservoirs, 1):
            details = self.config['controllers'][name]
            print(f"{i}. {name} - {details['description']} ({details['ip']})")
            
        while True:
            try:
                choice = int(input("\nSelect reservoir (or 0 to cancel): "))
                if choice == 0:
                    return None
                if 1 <= choice <= len(reservoirs):
                    selected = reservoirs[choice-1]
                    print(f"\nSelected {selected}")
                    return selected
            except ValueError:
                print("Please enter a valid number")
                
    async def connect_to_reservoir(self, reservoir_name):
        """Establish connection to selected reservoir"""
        if not reservoir_name in self.config['controllers']:
            print(f"Error: Unknown reservoir {reservoir_name}")
            return False
            
        self.connected_reservoir = reservoir_name
        print(f"\nConnected to {reservoir_name}")
        return True
        
    async def listen_for_data(self):
        """Listen for incoming data from reservoir"""
        if not self.connected_reservoir:
            print("Error: Not connected to any reservoir")
            return
            
        reservoir_ip = self.config['controllers'][self.connected_reservoir]['ip']
        uri = f"ws://{reservoir_ip}:{self.send_port}"
        
        print(f"\nListening for data from {self.connected_reservoir}...")
        self.is_listening = True
        
        try:
            async with websockets.connect(uri) as websocket:
                while self.is_listening:
                    try:
                        message = await websocket.recv()
                        data = json.loads(message)
                        if data['type'] == 'reservoir_output':
                            print(f"\nReceived data from {self.connected_reservoir}")
                            self.received_data.append(data['data'])
                            await self.save_output_data()
                    except websockets.exceptions.ConnectionClosed:
                        print("Connection closed by reservoir")
                        break
                    except Exception as e:
                        print(f"Error receiving data: {e}")
                        break
                        
        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            self.is_listening = False
            
    async def save_output_data(self):
        """Save received data to timestamped CSV file"""
        if not self.received_data:
            return
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"reservoir_output_{self.connected_reservoir}_{timestamp}.csv"
        output_path = self.output_dir / filename
        
        try:
            df = pd.DataFrame(self.received_data)
            df.to_csv(output_path, index=False)
            print(f"\nSaved output to {output_path}")
        except Exception as e:
            print(f"Error saving output: {e}")
            
    async def start_server(self):
        """Start WebSocket server to listen for acknowledgments"""
        try:
            self.server = await websockets.serve(
                self.handle_connection,
                "0.0.0.0",
                self.listen_port,
                ping_interval=None
            )
            print(f"\nListening for acknowledgments on port {self.listen_port}")
            
        except Exception as e:
            print(f"Error starting server: {e}")
            
    async def handle_connection(self, websocket):
        """Handle incoming acknowledgment messages"""
        try:
            async for message in websocket:
                data = json.loads(message)
                if data.get('type') == 'ready_signal':
                    if not self.waiting_for_ack:
                        print("\nWarning: Received ready signal while not waiting")
                        # Send rejection response
                        response = {
                            'status': 'error',
                            'message': 'Not waiting for acknowledgment'
                        }
                        await websocket.send(json.dumps(response))
                        continue
                        
                    print("\nReceived ready signal from trainer")
                    self.waiting_for_ack = False
                    
                    # Send success response and close connection
                    response = {
                        'status': 'success',
                        'message': 'Acknowledgment received'
                    }
                    await websocket.send(json.dumps(response))
                    break  # Exit the message loop after handling one acknowledgment
                    
        except Exception as e:
            print(f"Error handling connection: {e}")
            
    async def process_data_file(self, file_path):
        """Process a movement vector file and send to reservoir"""
        try:
            # Start acknowledgment server
            server = await websockets.serve(
                self.handle_connection,
                "0.0.0.0",
                self.listen_port,
                ping_interval=None
            )
            print(f"\nListening for acknowledgments on port {self.listen_port}")
            
            # Read CSV file
            print(f"\nReading file: {file_path}")
            df = pd.read_csv(file_path)
            
            # Verify data format
            roi_columns = []
            if 'roi_1_m0' in df.columns:
                roi_columns = [f'roi_1_m{i}' for i in range(30)]
            else:
                roi_columns = [f'ROI_1_{i+1}' for i in range(30)]
                
            time_columns = ['t_sin', 't_cos']
            
            if not all(col in df.columns for col in roi_columns + time_columns):
                print("Error: CSV file missing required columns")
                print("Required columns:", roi_columns + time_columns)
                print("Available columns:", df.columns.tolist())
                return False
            
            # Process each row
            total_rows = len(df)
            for i, row in df.iterrows():
                # Get movement values and scale to pot values
                movement_values = row[roi_columns].tolist()
                min_val = min(movement_values)
                max_val = max(movement_values)
                pot_values = [
                    self.scale_movement_log(val, min_val, max_val) 
                    for val in movement_values
                ]
                
                # Create data packet
                data_packet = {
                    'type': 'movement_data',
                    'timestamp': row['timestamp'] if 'timestamp' in row else str(datetime.now()),
                    'data': {
                        'pot_values': pot_values,
                        't_sin': float(row['t_sin']),
                        't_cos': float(row['t_cos'])
                    }
                }
                
                print(f"\nSending row {i+1}/{total_rows}")
                
                # Set waiting flag BEFORE sending
                self.waiting_for_ack = True
                
                # Send data and wait for initial response
                response = await self.input_node.send_data(
                    self.connected_reservoir,
                    data_packet
                )
                
                if response.get('status') == 'error':
                    print(f"\nError sending row {i+1}: {response.get('message')}")
                    return False
                
                # Wait for trainer's acknowledgment
                print("\nWaiting for trainer acknowledgment...")
                while self.waiting_for_ack:
                    await asyncio.sleep(0.1)  # Small sleep to prevent busy waiting
                    
                print("Received trainer acknowledgment, continuing...")
                await asyncio.sleep(10)  # Wait before next row
            
            # Clean up server
            server.close()
            await server.wait_closed()
            
            print("\nCompleted processing file")
            return True
            
        except Exception as e:
            print(f"\nError processing file: {e}")
            traceback.print_exc()  # Print full traceback
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

async def main():
    builder = ReservoirModelBuilder()
    
    while True:
        print("\nReservoir Model Builder")
        print("----------------------")
        print("1. Select reservoir node")
        print("2. Process movement data")
        print("3. Start listening for output")
        print("4. Stop listening")
        print("5. Exit")
        
        choice = input("\nEnter choice: ").strip()
        
        if choice == '1':
            reservoir = builder.select_reservoir()
            if reservoir:
                await builder.connect_to_reservoir(reservoir)
                
        elif choice == '2':
            if not builder.connected_reservoir:
                print("\nPlease select a reservoir first!")
                continue
                
            files = builder.list_available_data()
            if files:
                try:
                    file_num = int(input("\nSelect file number: "))
                    if 1 <= file_num <= len(files):
                        await builder.process_data_file(files[file_num-1])
                except ValueError:
                    print("Invalid selection")
                    
        elif choice == '3':
            if not builder.connected_reservoir:
                print("\nPlease select a reservoir first!")
                continue
            builder.is_listening = True
            await builder.listen_for_data()
            
        elif choice == '4':
            builder.is_listening = False
            print("\nStopped listening")
            
        elif choice == '5':
            print("\nExiting...")
            break

if __name__ == "__main__":
    asyncio.run(main()) 