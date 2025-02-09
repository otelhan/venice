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

os.environ['QT_QPA_PLATFORM'] = 'xcb'  # Use X11 backend instead of Wayland

class StateHandler:
    def __init__(self):
        self.serial_port = None
        self.port_name = None
        self.baud_rate = 9600
        self.movement_buffer = []
        self.should_continue = True
        self.serial_queue = Queue()
        self.serial_thread = None
        self.serial = None
        
        # Initialize camera
        self.camera = cv2.VideoCapture(0)
        if not self.camera.isOpened():
            print("ERROR: Could not open camera")
        
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

    def drive_wavemaker(self):
        """Drive the wavemaker with movement data"""
        if not self.serial:
            print("ERROR: No serial connection to KB2040")
            return True
            
        try:
            print("=== Starting wavemaker control ===")
            print(f"Processing {len(self.movement_buffer)} movements")
            
            # Initialize previous frame
            self.prev_frame = None
            
            for movement in self.movement_buffer:
                # Scale movement to motor range
                scaled_movement = self.scale_movement(movement)
                
                # Send movement value to KB2040
                command = f"{scaled_movement}\n"
                self.serial.write(command.encode())
                response = self.serial.readline().decode().strip()
                print(f"Original: {movement}, Scaled: {scaled_movement}, Response: {response}")
                
                # Update camera feed and calculate energy
                ret, frame = self.camera.read()
                if ret:
                    # Process frame and calculate energy
                    energy = self.calculate_frame_energy(frame)
                    
                    # Show processed frame
                    height, width = frame.shape[:2]
                    small_frame = cv2.resize(frame, (width//2, height//2))
                    gray_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
                    cv2.imshow('Camera Feed', gray_frame)
                    cv2.waitKey(1)
                    
                    # Update energy plot
                    self.update_energy_plot(energy)
                    plt.pause(0.001)
            
            # Set to max position when done
            final_command = "127\n"
            self.serial.write(final_command.encode())
            print("Setting wiper to maximum position")
            
            # Cleanup windows before returning
            cv2.destroyAllWindows()
            plt.close('all')
            
            return True
            
        except Exception as e:
            print(f"Error driving wavemaker: {e}")
            traceback.print_exc()
            
            # Cleanup on error
            cv2.destroyAllWindows()
            plt.close('all')
            
            return True

    def __del__(self):
        """Cleanup"""
        if self.camera is not None:
            self.camera.release()
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