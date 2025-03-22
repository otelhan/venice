import asyncio
import websockets
import json
import yaml
import os
import pandas as pd
from datetime import datetime
from enum import Enum
import numpy as np
from pathlib import Path

class TrainerState(Enum):
    IDLE = "IDLE"
    RECEIVING_DATA = "RECEIVING_DATA"
    TRAINING_MODEL = "TRAINING_MODEL"
    SAVING_MODEL = "SAVING_MODEL"
    SENDING_OUTPUT = "SENDING_OUTPUT"

class ReservoirTrainer:
    def __init__(self):
        self.config = self._load_config()
        self.current_state = TrainerState.IDLE
        
        # Get trainer-specific config
        if self.config and 'controllers' in self.config:
            self.trainer_config = self.config['controllers'].get('trainer', {})
            print(f"\nTrainer config:", self.trainer_config)
        else:
            self.trainer_config = {}
            print("No trainer config found!")
            
        # Setup data storage
        self.data_dir = os.path.join('data', 'training')
        os.makedirs(self.data_dir, exist_ok=True)
        self.current_file = None
        
        # Track input node for signaling
        self.input_node_ip = self.config['controllers']['res00']['ip']
        
        # Add model directory
        self.model_dir = os.path.join('models')
        os.makedirs(self.model_dir, exist_ok=True)
        self.model = None
        
        # Listen on 8765 for res00, send on 8766 to builder
        self.listen_port = self.config['controllers']['trainer'].get('listen_port', 8765)
        self.send_port = self.config['controllers']['trainer'].get('send_port', 8766)
        
    def _load_config(self):
        """Load configuration from YAML"""
        try:
            config_path = os.path.join('config', 'controllers.yaml')
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return None
            
    def get_latest_file(self):
        """Get the latest training file from the data directory"""
        try:
            csv_files = list(Path(self.data_dir).glob('reservoir_training_*.csv'))
            if not csv_files:
                return None
            return str(max(csv_files, key=lambda x: x.stat().st_mtime))
        except Exception as e:
            print(f"Error finding latest file: {e}")
            return None

    def create_new_file(self):
        """Create a new CSV file for storing received data"""
        # First check for existing file
        latest_file = self.get_latest_file()
        if latest_file:
            print(f"\nAppending to existing file: {latest_file}")
            return latest_file
            
        # Create new file with current timestamp
        file_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"reservoir_training_{file_timestamp}.csv"
        filepath = os.path.join(self.data_dir, filename)
        
        # Create empty DataFrame with required columns
        df = pd.DataFrame(columns=[
            'timestamp',  # This will store the received data timestamp
            *[f'energy_value_{i}' for i in range(30)],
            *[f'pot_value_{i}' for i in range(30)],
            't_sin',
            't_cos'
        ])
        
        df.to_csv(filepath, index=False)
        print(f"\nCreated new training file: {filepath}")
        return filepath
        
    async def handle_received_data(self, data):
        """Handle received data from reservoir"""
        try:
            if self.current_state != TrainerState.RECEIVING_DATA:
                print(f"Cannot handle data in {self.current_state.value} state")
                return False
                
            # Extract data with better error handling
            timestamp = data.get('timestamp', 'No timestamp')
            if not isinstance(data.get('data'), dict):
                print("Error: Invalid data format received")
                print("Received data:", data)
                return False
                
            # Handle energy data from reservoir
            if data.get('type') == 'energy_data':
                # Use timestamp from received data
                timestamp = data.get('timestamp', 'No timestamp')  # Original timestamp from data
                energy_values = data['data'].get('energy_values', [])
                pot_values = data['data'].get('pot_values', [])
                t_sin = data['data'].get('t_sin', 0.0)
                t_cos = data['data'].get('t_cos', 0.0)
                
                # Print formatted data
                print("\n" + "="*50)
                print(f"Received Energy Data at {timestamp}")  # Show original timestamp
                print("-"*50)
                print("Energy Values:")
                for i in range(0, 30, 5):  # Print 5 values per line
                    values = energy_values[i:i+5]
                    print(f"{i:2d}-{i+4:2d}: {values}")
                print("\nPot Values:")
                for i in range(0, 30, 5):
                    values = pot_values[i:i+5]
                    print(f"{i:2d}-{i+4:2d}: {values}")
                print(f"Time Encoding: sin={t_sin:.3f}, cos={t_cos:.3f}")
                print("="*50)
                
                # Create or get file
                if not self.current_file:
                    self.current_file = self.create_new_file()
                
                # Save data with original timestamp
                row_data = {
                    'timestamp': timestamp,  # Use original timestamp from data
                    **{f'energy_value_{i}': val for i, val in enumerate(energy_values)},
                    **{f'pot_value_{i}': val for i, val in enumerate(pot_values)},
                    't_sin': t_sin,
                    't_cos': t_cos
                }
                
                # Append to CSV
                df = pd.DataFrame([row_data])
                df.to_csv(self.current_file, mode='a', header=False, index=False)
                
                # Signal builder to send next row
                await self.signal_input_node()
                return True
            else:
                print(f"Unexpected data type: {data.get('type')}")
                return False
                
        except Exception as e:
            print(f"Error handling received data: {e}")
            return False
            
    async def signal_input_node(self):
        """Signal builder that we're ready for next row"""
        try:
            builder_config = self.config['controllers'].get('builder')
            if not builder_config:
                print("Builder configuration not found!")
                return
                
            # Get builder's listen port, default to 8766 if not specified
            builder_listen_port = builder_config.get('listen_port', 8766)
            uri = f"ws://{builder_config['ip']}:{builder_listen_port}"
            print(f"Signaling builder at {uri}")
            
            async with websockets.connect(uri) as websocket:
                signal = {
                    'type': 'ready_signal',
                    'timestamp': datetime.now().isoformat(),
                    'source': 'trainer'
                }
                await websocket.send(json.dumps(signal))
                
                # Wait for response and handle it
                response = await websocket.recv()
                response_data = json.loads(response)
                if response_data.get('status') == 'error':
                    print(f"Builder rejected signal: {response_data.get('message')}")
                else:
                    print("Builder acknowledged signal")
                
        except Exception as e:
            print(f"Error signaling builder: {e}")
            
    async def train_model(self):
        """Train the reservoir model using collected data"""
        if self.current_state != TrainerState.TRAINING_MODEL:
            print(f"Cannot train in {self.current_state.value} state")
            return False
            
        try:
            print("\nTraining model...")
            if not self.current_file:
                print("No data file available for training")
                return False
                
            # Load training data
            df = pd.read_csv(self.current_file)
            print(f"Loaded {len(df)} rows of training data")
            
            # Add your model training code here
            await asyncio.sleep(2)  # Simulate training
            
            # Store trained model
            self.model = {"trained": True, "timestamp": datetime.now().isoformat()}
            
            print("Model training complete")
            return True
            
        except Exception as e:
            print(f"Error training model: {e}")
            return False
            
    async def save_model(self):
        """Save the trained model"""
        if self.current_state != TrainerState.SAVING_MODEL:
            print(f"Cannot save model in {self.current_state.value} state")
            return False
            
        try:
            if not self.model:
                print("No trained model to save")
                return False
                
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            model_file = os.path.join(self.model_dir, f'reservoir_model_{timestamp}.pkl')
            
            # Add your model saving code here
            # For example: torch.save(self.model, model_file)
            
            print(f"\nModel saved to: {model_file}")
            return True
            
        except Exception as e:
            print(f"Error saving model: {e}")
            return False
            
    async def start_server(self):
        """Start WebSocket server to listen for data"""
        try:
            async with websockets.serve(
                self.handle_connection, 
                "0.0.0.0",
                self.listen_port,  # Use listen_port
                ping_interval=None
            ) as server:
                print(f"\nTrainer listening on port {self.listen_port}")
                await asyncio.Future()
                
        except Exception as e:
            print(f"Server error: {e}")
            
    async def handle_connection(self, websocket):
        """Handle incoming WebSocket connections"""
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    
                    if data.get('type') == 'movement_data':
                        success = await self.handle_received_data(data)
                        response = {
                            'status': 'success' if success else 'error',
                            'message': 'Data processed' if success else 'Processing failed'
                        }
                        await websocket.send(json.dumps(response))
                        
                except Exception as e:
                    print(f"Error processing message: {e}")
                    await websocket.send(json.dumps({
                        'status': 'error',
                        'message': str(e)
                    }))
                    
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed normally")
            
    async def run(self):
        """Main run loop"""
        while True:
            print("\nReservoir Trainer")
            print("----------------")
            print("1. Start receiving data")
            print("2. Train model")
            print("3. Save model")
            print("4. Exit")
            
            choice = input("\nEnter choice: ").strip()
            
            if choice == '1':
                self.current_state = TrainerState.RECEIVING_DATA
                print("\nStarting data collection...")
                await self.start_server()
                
            elif choice == '2':
                self.current_state = TrainerState.TRAINING_MODEL
                await self.train_model()
                
            elif choice == '3':
                self.current_state = TrainerState.SAVING_MODEL
                await self.save_model()
                
            elif choice == '4':
                print("\nExiting...")
                break
                
            else:
                print("\nInvalid choice")

if __name__ == "__main__":
    trainer = ReservoirTrainer()
    asyncio.run(trainer.run()) 