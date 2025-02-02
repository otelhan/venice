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
        """Handle the DRIVE_WAVEMAKER state"""
        try:
            print("\n=== Starting wavemaker control ===")
            
            # Find and open serial port
            self.port_name = self.find_kb2040_port()
            if not self.port_name:
                print("ERROR: KB2040 not found!")
                return 'i'  # Return to IDLE if no device found
                
            self.serial_port = serial.Serial(
                port=self.port_name,
                baudrate=self.baud_rate,
                timeout=1
            )
            time.sleep(2)  # Wait for port to stabilize
            
            # Start serial thread
            self.should_continue = True
            self.serial_thread = threading.Thread(target=self.serial_worker)
            self.serial_thread.start()
            
            # Initialize plot
            plt.ion()  # Turn on interactive mode
            fig = plt.figure('Energy Plot')
            ax = fig.add_subplot(111)
            line, = ax.plot([], [], 'b-')
            ax.set_title('Movement Values')
            ax.set_xlabel('Sample')
            ax.set_ylabel('Motor Value')
            ax.grid(True)
            
            # Start camera
            if self.camera.start_camera():
                print("Press 'q' to stop camera feed")
                
                # Process movements
                if self.movement_buffer:
                    max_movement = max(self.movement_buffer)
                    
                    # Scale movements with minimum threshold of 20
                    scaled_movements = [max(20, min(127, int(m * 127 / max_movement))) 
                                     for m in self.movement_buffer]
                    
                    # Set plot limits
                    ax.set_xlim(0, len(scaled_movements))
                    ax.set_ylim(0, 130)  # Slightly above max motor value
                    line.set_data(range(len(scaled_movements)), scaled_movements)
                    fig.canvas.draw_idle()
                    plt.show(block=False)
                    
                    # Queue all values for serial thread
                    for value in scaled_movements:
                        self.serial_queue.put(value)
                    
                    # Keep updating camera until 'q' pressed or values finished
                    current_idx = 0
                    while self.should_continue:
                        if not self.camera.show_frame():
                            print("\nVideo window closed")
                            break
                        
                        # Update plot with current position
                        if not self.serial_queue.empty():
                            current_idx = len(scaled_movements) - self.serial_queue.qsize()
                            line.set_data(range(len(scaled_movements)), scaled_movements)
                            ax.axvline(x=current_idx, color='r', linestyle='--', alpha=0.5)
                            fig.canvas.draw_idle()
                            fig.canvas.flush_events()
                        
                        # Check if we've processed all values
                        if self.serial_queue.empty():
                            print("\nFinished processing all values")
                            break
                        
                        # Add small delay to prevent CPU overload
                        cv2.waitKey(1)
                            
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            
        finally:
            print("\nCleaning up resources...")
            # Cleanup
            self.should_continue = False
            
            # Wait for serial thread to finish
            if self.serial_thread:
                self.serial_thread.join()
                
            # Close serial port
            if self.serial_port:
                try:
                    self.serial_port.write(b"127\n")  # Reset motor
                    self.serial_port.close()
                except:
                    pass
                self.serial_port = None
                
            # Close camera and windows
            print("Stopping camera...")
            self.camera.stop_camera()
            print("Closing windows...")
            cv2.destroyAllWindows()
            plt.close('Energy Plot')
            cv2.waitKey(1)  # Force window updates
            
            print("Cleanup complete")
            # Return to IDLE state
            return 'i'  # Signal to transition to IDLE state
    
    def __del__(self):
        """Cleanup when object is destroyed"""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()