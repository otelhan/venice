import serial # type: ignore
import serial.tools.list_ports
import time
from .video_processor import VideoProcessor
import numpy as np
from .camera_handler import CameraHandler
import matplotlib.pyplot as plt
import cv2
import threading
from queue import Queue
import os
import traceback
from src.core.states import MachineState
import json
import websockets
import asyncio

os.environ['QT_QPA_PLATFORM'] = 'xcb'  # Use X11 backend instead of Wayland

class StateHandler:
    def __init__(self, display_config=None, controller_config=None, full_config=None):
        self.serial_port = None
        self.port_name = None
        self.baud_rate = 9600
        self.movement_buffer = []
        self.should_continue = True
        self.serial_queue = Queue()
        self.serial_thread = None
        self.serial = None
        self.display_config = display_config or {}
        self.config = controller_config  # Store controller-specific config
        self.full_config = full_config or {}  # Store full config with all controllers
        
        print(f"StateHandler config: {self.config}")
        print(f"StateHandler destination: {self.config.get('destination', 'None')}")
        
        # Initialize camera
        self.camera = None
        if self.display_config.get('show_camera', False):
            self.camera = CameraHandler(self.display_config)
        
        # Remove the wavemaker plot setup
        self.energy_values = []
        self.window_size = 100
        
        # Outgoing buffer for collected energy values
        self.outgoing_buffer = {
            'movements': [],  # Store movement commands (20-127)
            'energy_values': [],  # Store corresponding energy readings
            'timestamps': []  # Store timestamps for each reading
        }
        self.max_buffer_size = 30  # Maximum number of values to store
        
    def find_kb2040_port(self):
        """Find the KB2040 port"""
        for port in serial.tools.list_ports.comports():
            if 'usbmodem' in port.device.lower():  # KB2040 usually shows up with 'usbmodem'
                return port.device
        return None
        
    def collect_signal(self):
        """Handle the COLLECT_SIGNAL state"""
        print("\n=== Starting signal collection ===")
        
        # Make sure camera is stopped when entering collect_signal
        self.camera.stop_camera()
        
        # Always reinitialize video
        self.processor.load_video("input_videos/Ponte delle Guglie_night.mp4")
        self.processor.select_roi()
        
        # Collect for 10 seconds (assuming 30fps video)
        frames_to_collect = 300  # 10 seconds * 30 frames
        movements = self.processor.calculate_movement(max_frames=frames_to_collect)
        
        if movements:
            self.movement_buffer.extend(movements)
            print(f"\nCollected {len(movements)} new measurements")
            
            # Handle command input here
            while True:
                print("\nEnter 'd' for drive wavemaker, 'q' to quit: ")
                command = input().strip().lower()
                if command in ['d', 'q']:
                    return command

    def serial_worker(self):
        """Worker thread for serial communication"""
        while self.should_continue:
            try:
                if not self.serial_queue.empty():
                    value = self.serial_queue.get()
                    value_str = f"{value}\n"
                    self.serial_port.write(value_str.encode())
                    response = self.serial_port.readline().decode().strip()
                    print(f"Sent: {value}, Response: {response}")
                time.sleep(0.2)  # Prevent busy waiting
            except Exception as e:
                print(f"Serial error: {e}")
                break
                
    def calculate_frame_energy(self, frame):
        """Calculate frame energy using ROI and movement detection.
        This is only used for video input not camera"""
        
        try:
            # Scale down frame
            height, width = frame.shape[:2]
            small_frame = cv2.resize(frame, (width//2, height//2))
            
            # Convert to grayscale
            gray_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            
            # If this is first frame, initialize previous frame
            if self.prev_frame is None:
                self.prev_frame = gray_frame
                return 0
            
            # Calculate absolute difference between frames
            frame_diff = cv2.absdiff(gray_frame, self.prev_frame)
            
            # Update previous frame
            self.prev_frame = gray_frame
            
            # Calculate mean movement
            movement = np.mean(frame_diff)
            
            return movement
            
        except Exception as e:
            print(f"Error calculating frame energy: {e}")
            return 0

    def scale_movement(self, value):
        """Scale movement value to motor range (20-127)"""
        try:
            # Scale to range 20-127
            scaled = int(20 + (value * (127 - 20) / 255))
            # Ensure limits
            return max(20, min(127, scaled))
        except Exception as e:
            print(f"Error scaling movement: {e}")
            return 127  # Default to max on error

    def drive_wavemaker(self):
        """Drive the wavemaker with movement data"""
        if not self.serial:
            print("ERROR: No serial connection to KB2040")
            return True
        
        try:
            print("=== Starting wavemaker control ===")
            print(f"Processing {len(self.movement_buffer)} movements")
            
            # Start camera
            self.camera.start_camera()
            
            # Turn on wavemaker
            print("\nTurning wavemaker ON...")
            self.serial.write(b"on\n")
            response = self.serial.readline().decode().strip()
            print(f"Wavemaker ON response: {response}")
            
            time.sleep(1)  # Wait after turning on
            
            # Process each movement
            for i, movement in enumerate(self.movement_buffer, 1):
                # Send movement value to KB2040
                command = f"{movement}\n"
                print(f"\nSending movement {i}/30: {movement}")
                self.serial.write(command.encode())
                response = self.serial.readline().decode().strip()
                print(f"Response: {response}")
                
                # Capture and process frame
                frame = self.camera.get_frame()
                if frame is not None:
                    energy = self.camera.calculate_frame_energy(frame)
                    print(f"Frame {i} energy: {energy:.2f}")
                    
                    # Store in outgoing buffer
                    self.outgoing_buffer['movements'].append(movement)
                    self.outgoing_buffer['energy_values'].append(energy)
                    self.outgoing_buffer['timestamps'].append(time.time())
                    
                    # Maintain buffer size
                    if len(self.outgoing_buffer['movements']) > self.max_buffer_size:
                        self.outgoing_buffer['movements'].pop(0)
                        self.outgoing_buffer['energy_values'].pop(0)
                        self.outgoing_buffer['timestamps'].pop(0)
                    
                    # Update plot
                    self.camera.update_energy_plot(energy)
                
                time.sleep(1)  # Wait between movements
            
            return True
            
        except Exception as e:
            print(f"Error driving wavemaker: {e}")
            return True
        finally:
            # Turn off wavemaker
            try:
                print("\nTurning wavemaker OFF...")
                self.serial.write(b"off\n")
            except:
                pass

    def __del__(self):
        """Cleanup when object is destroyed"""
        if hasattr(self, 'camera'):
            self.camera.stop_camera()
        cv2.destroyAllWindows()
        plt.close('all')

    def update_energy_plot(self, value):
        """Update the energy plot"""
        try:
            self.energy_values.append(value)
            if len(self.energy_values) > self.window_size:
                self.energy_values = self.energy_values[-self.window_size:]
                
            start_idx = max(0, len(self.energy_values) - self.window_size)
            xdata = range(start_idx, start_idx + len(self.energy_values))
            self.line.set_data(xdata, self.energy_values)
            self.ax.set_xlim(start_idx, start_idx + self.window_size)
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()
            
        except Exception as e:
            print(f"Error updating plot: {e}")

    async def send_data(self, destination):
        """Send collected data to destination controller"""
        try:
            print(f"\nPreparing to send data to {destination}")
            
            # Get destination controller config from full config
            if not self.full_config or 'controllers' not in self.full_config:
                print("No controller configuration found!")
                print("Config:", self.config)
                return False
            
            dest_config = self.full_config['controllers'].get(destination)
            if not dest_config:
                print(f"Unknown destination controller: {destination}")
                print("Available controllers:", list(self.full_config['controllers'].keys()))
                return False
            
            # Print connection details
            print(f"Destination IP: {dest_config['ip']}")
            print(f"Destination MAC: {dest_config['mac']}")
            
            # Send to destination with connection timeout and retries
            uri = f"ws://{dest_config['ip']}:8765"
            print(f"Connecting to: {uri}")
            
            max_connection_attempts = 2
            connection_timeout = 3
            
            for attempt in range(max_connection_attempts):
                print(f"\nConnection attempt {attempt + 1}/{max_connection_attempts}")
                try:
                    # Use asyncio.wait_for for the entire connection attempt
                    async with await asyncio.wait_for(
                        websockets.connect(uri), 
                        timeout=connection_timeout
                    ) as websocket:
                        try:
                            await asyncio.wait_for(
                                websocket.send(json.dumps(self.outgoing_buffer)),
                                timeout=3  # 3 second timeout for send
                            )
                            response = await asyncio.wait_for(
                                websocket.recv(),
                                timeout=3  # 3 second timeout for receive
                            )
                            print(f"Response from {destination}: {response}")
                            return True
                            
                        except asyncio.TimeoutError:
                            print(f"Timeout waiting for response from {destination}")
                            continue  # Try next connection attempt
                            
                except (asyncio.TimeoutError,
                        websockets.exceptions.ConnectionError, 
                        websockets.exceptions.InvalidStatusCode,
                        ConnectionRefusedError) as e:
                    print(f"Connection attempt {attempt + 1} failed: {e}")
                    if attempt < max_connection_attempts - 1:
                        print("Retrying connection...")
                        await asyncio.sleep(1)  # Wait 1 second between attempts
                    continue
                
            print(f"Failed to connect to {destination} after {max_connection_attempts} attempts")
            return False
            
        except Exception as e:
            print(f"Error sending data: {e}")
            return False