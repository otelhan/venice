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
        uri = f"ws://{reservoir_ip}:8765"
        
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
            
    async def process_data_file(self, file_path):
        """Process a movement vector file and send to reservoir"""
        try:
            # Read CSV file
            df = pd.read_csv(file_path)
            print(f"\nProcessing {file_path.name}")
            
            # Handle both naming formats (roi_1_m0 and ROI_1_1)
            roi_columns = []
            if 'roi_1_m0' in df.columns:  # Check for m0 format
                roi_columns = [f'roi_1_m{i}' for i in range(30)]
            else:  # Try ROI format
                roi_columns = [f'ROI_1_{i+1}' for i in range(30)]
            
            time_columns = ['t_sin', 't_cos']
            
            # Verify columns exist
            if not all(col in df.columns for col in roi_columns + time_columns):
                print("Error: CSV file missing required columns")
                print("Required columns:", roi_columns + time_columns)
                print("Available columns:", df.columns.tolist())
                return False
            
            # Select only ROI_1 and time encoding columns
            data_df = df[roi_columns + time_columns]
            total_rows = len(data_df)
            print(f"Found {total_rows} movement vectors")
            
            # Process each row with delay
            for i, row in data_df.iterrows():
                # Get movement values as a list
                movements = row[roi_columns].tolist()
                
                # Print first data packet
                if i == 0:
                    print("\nFirst data packet to be sent:")
                    print("\nPacket format:")
                    print("[", end='')
                    # First timestamp
                    print(f"{row['timestamp'] if 'timestamp' in row else 'N/A'}, ", end='')
                    # Then 30 movement values
                    for i, val in enumerate(movements):
                        print(f"{val:.6f}", end='')
                        print(", ", end='')
                    # Finally t_sin and t_cos
                    print(f"{row['t_sin']:.6f}, ", end='')
                    print(f"{row['t_cos']:.6f}", end='')
                    print("]")
                    print("\nOrder: [timestamp, 30 movement values, t_sin, t_cos]")
                    print("Length:", len(movements) + 3)  # timestamp + 30 movements + 2 time values
                    input("\nPress Enter to start sending data...")
                
                # Send to reservoir
                print(f"\rSending row {i+1}/{total_rows}", end='')
                
                # Send movements directly like test_reservoir_driver
                self.input_node.movement_buffer = movements
                response = await self.input_node.send_movement_data(self.connected_reservoir)
                
                if response.get('status') == 'error':
                    print(f"\nError sending row {i+1}: {response.get('message')}")
                    return False
                
                # Wait 10 seconds before next row
                await asyncio.sleep(10)
            
            print("\nCompleted processing file")
            return True
            
        except Exception as e:
            print(f"\nError processing file: {e}")
            return False

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