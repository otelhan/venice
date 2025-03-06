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

os.environ['QT_QPA_PLATFORM'] = 'xcb'  # Use X11 backend instead of Wayland

class StateHandler:
    def __init__(self, display_config=None):
        self.serial_port = None
        self.port_name = None
        self.baud_rate = 9600
        self.movement_buffer = []
        self.should_continue = True
        self.serial_queue = Queue()
        self.serial_thread = None
        self.serial = None
        
        # Initialize camera
        self.camera = CameraHandler(display_config)
        if not self.camera.is_running:
            print("WARNING: Camera not initialized")
        
        # Setup energy plot
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(8, 4))
        self.line, = self.ax.plot([], [], 'b-', linewidth=2)
        self.ax.set_ylim(0, 255)
        self.ax.set_xlabel('Frame')
        self.ax.set_ylabel('Movement Value')
        self.ax.set_title('Wavemaker Control Values')
        self.ax.grid(True)
        self.energy_values = []
        self.window_size = 100
        plt.show()
        
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
        """Calculate frame energy using ROI and movement detection"""
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

    async def drive_wavemaker(self):
        """Drive the wavemaker with movement data"""
        if not self.serial:
            print("ERROR: No serial connection to KB2040")
            return True
            
        try:
            print("=== Starting wavemaker control ===")
            print(f"Processing {len(self.movement_buffer)} movements")
            
            # Initialize energy collection
            energy_values = []
            
            # Start camera if display enabled
            if self.camera.show_display:
                self.camera.start_camera()
            
            # Turn on wavemaker first
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
                
                # Always capture and process frame for energy calculation
                frame = self.camera.get_frame()
                if frame is not None:
                    energy = self.camera.calculate_frame_energy(frame)
                    print(f"Frame {i} energy: {energy:.2f}")
                    
                    # Scale energy to motor range (20-127)
                    scaled_energy = int(20 + (energy * (127 - 20) / 8))  # Assuming max energy is ~8
                    scaled_energy = max(20, min(127, scaled_energy))
                    energy_values.append(scaled_energy)
                    
                    # Only show visual output if display is enabled
                    if self.camera.show_display:
                        self.camera.update_energy_plot(energy)
                        if self.camera.show_camera:
                            self.camera.show_frame()
                
                time.sleep(1)  # Wait between movements
            
            # Turn off wavemaker
            print("\nTurning wavemaker OFF...")
            self.serial.write(b"off\n")
            response = self.serial.readline().decode().strip()
            print(f"Wavemaker OFF response: {response}")
            
            # Forward energy data to destination if configured
            if energy_values and 'destination' in self.config:
                dest = self.config['destination']
                print(f"\nForwarding {len(energy_values)} energy values to {dest}")
                
                data_packet = {
                    'type': 'data',
                    'data': {
                        'movements': energy_values
                    },
                    'timestamp': time.time(),
                    'metadata': {
                        'source': self.controller_name,
                        'type': 'energy_values',
                        'count': len(energy_values)
                    }
                }
                
                try:
                    # Get destination controller config
                    dest_controller = self.config['controllers'][dest]
                    uri = f"ws://{dest_controller['ip']}:8765"
                    
                    async with websockets.connect(uri) as websocket:
                        await websocket.send(json.dumps(data_packet))
                        response = await websocket.recv()
                        print(f"Forward response: {response}")
                except Exception as e:
                    print(f"Error forwarding to {dest}: {e}")
            
            return True
            
        except Exception as e:
            print(f"Error driving wavemaker: {e}")
            traceback.print_exc()
            try:
                self.serial.write(b"off\n")  # Make sure to turn off on error
            except:
                pass
            return True
        finally:
            self.camera.stop_camera()

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