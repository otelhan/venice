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

os.environ['QT_QPA_PLATFORM'] = 'xcb'  # Use X11 backend instead of Wayland

class StateHandler:
    def __init__(self):
        self.serial_port = None
        self.port_name = None  # We'll find this dynamically
        self.baud_rate = 9600
        self.movement_buffer = []
        self.processor = VideoProcessor()
        self.should_continue = True
        self.camera = CameraHandler()
        self.serial_queue = Queue()
        self.serial_thread = None
        self.serial = None
        self.window_name = "Camera View"
        self.is_running = False
        
        # Add energy plotting setup
        self.energy_values = []
        self.window_size = 100
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(8, 4))
        self.line, = self.ax.plot([], [], 'b-', linewidth=2)
        self.ax.set_ylim(0, 255)
        self.ax.set_xlabel('Frame')
        self.ax.set_ylabel('Movement Value')
        self.ax.grid(True)
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
                
    def drive_wavemaker(self):
        """Drive the wavemaker with movement data"""
        if not self.serial:
            print("ERROR: No serial connection to KB2040")
            return True
            
        try:
            print("=== Starting wavemaker control ===")
            print(f"Processing {len(self.movement_buffer)} movements")
            
            # Make sure windows are created
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            plt.figure('Energy Plot')  # Create or focus plot window
            
            for movement in self.movement_buffer:
                # Send movement value to KB2040
                command = f"{int(movement)}\n"
                self.serial.write(command.encode())
                response = self.serial.readline().decode().strip()
                print(f"Sent: {movement}, Response: {response}")
                
                # Update displays
                if self.camera and self.is_running:
                    ret, frame = self.camera.read()
                    if ret:
                        cv2.imshow(self.window_name, frame)
                        cv2.waitKey(1)
                        
                # Update plot
                self.update_energy_plot(movement)
                plt.pause(0.001)  # Allow plot to update
                
            return True
            
        except Exception as e:
            print(f"Error driving wavemaker: {e}")
            return True
    
    def __del__(self):
        """Cleanup when object is destroyed"""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()

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