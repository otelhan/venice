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
            # Get configured ports
            self.listen_port = self.trainer_config.get('listen_port', 8765)  # Default to 8765
            self.send_port = self.trainer_config.get('send_port', 8766)      # Default to 8766
            print(f"\nTrainer config:", self.trainer_config)
            print(f"Listening on port: {self.listen_port}")
            print(f"Sending on port: {self.send_port}")
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
            
        # Create new file if none exists
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"reservoir_training_{timestamp}.csv"
        filepath = os.path.join(self.data_dir, filename)
        
        # Create empty DataFrame with required columns
        df = pd.DataFrame(columns=[
            'timestamp',
            *[f'pot_value_{i}' for i in range(30)],
            't_sin',
            't_cos'
        ])
        
        df.to_csv(filepath, index=False)
        print(f"\nCreated new training file: {filepath}")
        return filepath
        
    async def handle_message(self, websocket, data):
        """Handle incoming messages"""
        try:
            if data.get('type') == 'movement_data':
                print("\nReceived movement data")
                
                # Save data to CSV
                timestamp = data['timestamp']
                pot_values = data['data']['pot_values']
                t_sin = data['data']['t_sin'] 
                t_cos = data['data']['t_cos']
                
                # Create/append to CSV file
                if not self.current_file:
                    filename = f"reservoir_training_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    self.current_file = os.path.join(self.data_dir, filename)
                    
                # Save to CSV
                self.save_to_csv(timestamp, pot_values, t_sin, t_cos)
                
                # Send acknowledgment back
                response = {
                    'status': 'success',
                    'message': 'Data processed'
                }
                await websocket.send(json.dumps(response))

                # Signal builder we're ready for next data
                builder_uri = f"ws://{self.config['controllers']['builder']['ip']}:{self.config['controllers']['builder']['port']}"
                async with websockets.connect(builder_uri) as builder_ws:
                    signal = {
                        'type': 'ready_signal',
                        'timestamp': datetime.now().isoformat()
                    }
                    await builder_ws.send(json.dumps(signal))
            
        except Exception as e:
            print(f"Error handling message: {e}")
            await websocket.send(json.dumps({
                'status': 'error',
                'message': str(e)
            }))
            
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
                        print("\nReceived data packet:")
                        print(json.dumps(data, indent=2))  # Print full packet for verification
                        
                        # Verify data structure
                        if not all(key in data.get('data', {}) for key in ['pot_values', 't_sin', 't_cos']):
                            print("Error: Invalid data format - missing required fields")
                            await websocket.send(json.dumps({
                                'status': 'error',
                                'message': 'Invalid data format'
                            }))
                            continue
                            
                        await self.handle_message(websocket, data)
                        
                    else:
                        print(f"Unexpected message type: {data.get('type')}")
                        await websocket.send(json.dumps({
                            'status': 'error',
                            'message': f"Unexpected message type: {data.get('type')}"
                        }))
                        
                except json.JSONDecodeError:
                    print("Error: Invalid JSON format")
                    await websocket.send(json.dumps({
                        'status': 'error',
                        'message': 'Invalid JSON format'
                    }))
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