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
    PROCESSING_DATA = "PROCESSING_DATA"
    SENDING_ACK = "SENDING_ACK"
    TRAINING_MODEL = "TRAINING_MODEL"
    SAVING_MODEL = "SAVING_MODEL"

class ReservoirTrainer:
    def __init__(self):
        self.config = self._load_config()
        self.current_state = TrainerState.IDLE
        
        # Get trainer-specific config
        if self.config and 'controllers' in self.config:
            self.trainer_config = self.config['controllers'].get('trainer', {})
            # Get configured ports
            self.listen_port = self.trainer_config.get('listen_port', 8765)
            self.send_port = self.trainer_config.get('send_port', 8766)
            print(f"\nTrainer config:", self.trainer_config)
            print(f"Listening on port: {self.listen_port}")
            print(f"Sending on port: {self.send_port}")
            
            # Get builder config for acknowledgements
            builder_config = self.config['controllers'].get('builder')
            if builder_config:
                self.builder_ip = builder_config['ip']
                self.builder_port = builder_config.get('listen_port', 8766)
            else:
                print("Warning: No builder configuration found")
        else:
            print("Error: No trainer configuration found!")
            raise ValueError("Missing trainer configuration")
            
        # Setup data storage
        self.data_dir = os.path.join('data', 'training')
        os.makedirs(self.data_dir, exist_ok=True)
        self.current_file = None
        
        self.processed_timestamps = set()  # Track processed timestamps
        
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
                
                # Check for duplicate timestamp
                timestamp = data['timestamp']
                if timestamp in self.processed_timestamps:
                    print(f"Already processed data with timestamp: {timestamp}")
                    response = {
                        'status': 'success',  # Still return success to avoid retries
                        'message': 'Data already processed'
                    }
                    await websocket.send(json.dumps(response))
                    return
                
                # Save data to CSV
                pot_values = data['data']['pot_values']
                t_sin = data['data']['t_sin'] 
                t_cos = data['data']['t_cos']
                
                # Create/append to CSV file
                if not self.current_file:
                    filename = f"movement_vectors_{timestamp.split()[0].replace('-','')}.csv"
                    self.current_file = os.path.join(self.data_dir, filename)
                    
                # Save to CSV
                self.save_to_csv(data)
                
                # Add timestamp to processed set
                self.processed_timestamps.add(timestamp)
                
                # Send acknowledgment back
                response = {
                    'status': 'success',
                    'message': 'Data processed'
                }
                await websocket.send(json.dumps(response))
                
                # Signal we're ready for next data
                await self.signal_input_node()
            
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
        """Start websocket server to receive data"""
        try:
            self.transition_to(TrainerState.IDLE)  # Start in IDLE state
            print(f"\nStarting server on port {self.listen_port}")
            
            async with websockets.serve(
                self.handle_connection, 
                "0.0.0.0", 
                self.listen_port
            ):
                await asyncio.Future()  # run forever
                
        except Exception as e:
            print(f"Error starting server: {e}")
            self.transition_to(TrainerState.IDLE)
            
    async def handle_connection(self, websocket):
        """Handle incoming WebSocket connections"""
        try:
            async for message in websocket:
                try:
                    # Switch to RECEIVING_DATA when getting a message
                    self.transition_to(TrainerState.RECEIVING_DATA)
                    data = json.loads(message)
                    
                    if data.get('type') == 'movement_data':
                        print("\nReceived data packet:")
                        print(json.dumps(data, indent=2))
                        
                        # Verify data structure
                        if not all(key in data.get('data', {}) for key in ['pot_values', 't_sin', 't_cos']):
                            print("Error: Invalid data format - missing required fields")
                            await websocket.send(json.dumps({
                                'status': 'error',
                                'message': 'Invalid data format'
                            }))
                            self.transition_to(TrainerState.IDLE)
                            continue

                        # Send success response to the sender
                        await websocket.send(json.dumps({
                            'status': 'success',
                            'message': 'Data received'
                        }))
                        
                        # Get sender's IP
                        sender_ip = websocket.remote_address[0]
                        # Handle the data and send acknowledgement if needed
                        await self.handle_movement_data(data, source_ip=sender_ip)
                        
                    else:
                        print(f"Unexpected message type: {data.get('type')}")
                        await websocket.send(json.dumps({
                            'status': 'error',
                            'message': f"Unexpected message type: {data.get('type')}"
                        }))
                        self.transition_to(TrainerState.IDLE)
                        
                except json.JSONDecodeError:
                    print("Error: Invalid JSON format")
                    await websocket.send(json.dumps({
                        'status': 'error',
                        'message': 'Invalid JSON format'
                    }))
                    self.transition_to(TrainerState.IDLE)
                    
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed normally")
            self.transition_to(TrainerState.IDLE)

    def save_to_csv(self, data):
        """Save received data to CSV"""
        try:
            # Extract data from the message
            timestamp = data.get('timestamp')
            pot_values = data['data']['pot_values']
            t_sin = data['data']['t_sin']
            t_cos = data['data']['t_cos']
            
            # Create row data dictionary
            row_data = {
                'timestamp': timestamp,
                **{f'pot_value_{i}': val for i, val in enumerate(pot_values)},
                't_sin': t_sin,
                't_cos': t_cos
            }
            
            # Convert to DataFrame and save
            df = pd.DataFrame([row_data])
            
            # Create file if it doesn't exist
            if not self.current_file:
                self.current_file = self.create_new_file()
            
            # Append to CSV
            df.to_csv(self.current_file, mode='a', header=False, index=False)
            print(f"Data saved to {self.current_file}")
            
            # Mark timestamp as processed
            self.processed_timestamps.add(timestamp)
            
        except Exception as e:
            print(f"Error saving to CSV: {e}")
            raise

    async def handle_movement_data(self, data, source_ip=None):
        """Handle incoming movement data from any source"""
        try:
            self.transition_to(TrainerState.RECEIVING_DATA)
            
            # Process the data
            self.transition_to(TrainerState.PROCESSING_DATA)
            
            # Check if we've already processed this data
            timestamp = data.get('timestamp')
            if timestamp in self.processed_timestamps:
                print(f"Already processed data with timestamp: {timestamp}")
                self.transition_to(TrainerState.IDLE)  # Return to IDLE if already processed
                return
            
            # Save to CSV
            self.save_to_csv(data)
            
            # Send acknowledgement back to builder
            self.transition_to(TrainerState.SENDING_ACK)
            await self.send_acknowledgement(timestamp)
            
            # Return to IDLE
            self.transition_to(TrainerState.IDLE)
            
        except Exception as e:
            print(f"Error handling movement data: {e}")
            self.transition_to(TrainerState.IDLE)
            raise

    def transition_to(self, new_state):
        """Transition to a new state"""
        print(f"\nTrainer transitioning from {self.current_state.name} to {new_state.name}")
        self.current_state = new_state

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
                print("\nStarting data collection...")
                await self.start_server()
                
            elif choice == '2':
                self.transition_to(TrainerState.TRAINING_MODEL)
                await self.train_model()
                
            elif choice == '3':
                self.transition_to(TrainerState.SAVING_MODEL)
                await self.save_model()
                
            elif choice == '4':
                print("\nExiting...")
                break
                
            else:
                print("\nInvalid choice")

    async def send_acknowledgement(self, timestamp):
        """Send acknowledgement back to builder"""
        try:
            builder_config = self.config['controllers'].get('builder')
            if not builder_config:
                print("No builder configuration found")
                return False
                
            uri = f"ws://{builder_config['ip']}:{builder_config['listen_port']}"
            print(f"\nSending acknowledgement to builder at {uri}")
            
            async with websockets.connect(uri) as websocket:
                ack = {
                    'type': 'ack',
                    'timestamp': timestamp,
                    'status': 'success'
                }
                await websocket.send(json.dumps(ack))
                print("Acknowledgement sent to builder")
                return True
                
        except Exception as e:
            print(f"Error sending acknowledgement: {e}")
            return False

if __name__ == "__main__":
    trainer = ReservoirTrainer()
    asyncio.run(trainer.run()) 