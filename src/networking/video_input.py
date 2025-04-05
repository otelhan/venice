import cv2
import numpy as np
from typing import Optional, Dict, Tuple
import time
import yt_dlp
import yaml
import os
from pathlib import Path
from datetime import datetime
import pandas as pd
import csv
import pytz  # Added for timezone handling
import websockets  # Add this import at the top
import json
import asyncio

# Use cocoa backend for Mac, xcb for Linux
# if os.uname().sysname == 'Darwin':  # macOS
#     os.environ['QT_QPA_PLATFORM'] = 'cocoa'
# else:  # Linux
#     os.environ['QT_QPA_PLATFORM'] = 'xcb'

class VideoInput:
    def __init__(self):
        self.stream = None
        self.cap = None
        self.frame_count = 0
        self.last_frame = None
        self.is_running = False
        self.config = self.load_config()
        self.roi_configs = self.config['video_input']['roi_configs']
        self.rois = {}  # Store ROI frames
        self.movement_buffers = {f'roi_{i+1}': [] for i in range(4)}
        self.last_frame_time = 0
        self.last_vector_time = 0
        self.selected_cells = []
        self.cell_size = 40
        self.scale_factor = 1.0
        self.show_rois = True  # Toggle for ROI display
        self.calculating = False  # Initialize calculation state
        self.save_needed = False  # Flag for when saving is needed
        
        # Frame buffer for movement calculation
        self.frame_buffer = []
        self.buffer_size = 3  # Keep 3 frames for rate of change calculation
        self.movement_threshold = 5  # Threshold for movement detection
        
        # Movement calculation timing
        self.frame_interval = 1.0  # Capture one frame per second
        self.vector_interval = 30.0  # Calculate movement vectors every 30 seconds
        
        # Get sampling config if available
        sampling_config = self.config['video_input'].get('sampling', {})
        if sampling_config:
            # Override defaults with config values if present
            self.frame_interval = float(sampling_config.get('frame_interval', self.frame_interval))
            self.vector_interval = float(sampling_config.get('vector_interval', self.vector_interval))
            
        # Save interval can be different from vector calculation interval
        self.save_interval = float(sampling_config.get('save_interval', self.vector_interval))
        print(f"Movement calculation interval: {self.vector_interval} seconds")
        print(f"CSV save interval: {self.save_interval} seconds")
        
        # Add timestamps for tracking intervals
        self.last_vector_time = time.time()  # Last time vectors were calculated
        self.last_save_time = time.time()    # Last time data was saved to CSV
        
        # Movement buffers
        self.vector_size = 30  # Store 30 values per ROI
        
        # Add Venice timezone
        self.venice_tz = pytz.timezone('Europe/Rome')  # Venice uses same timezone as Rome

        # Add reconnection settings
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        self.stream_timeout = 30  # seconds
        self.last_frame_success = time.time()

        # Add controller connection config - get from config file
        self.destination = self.config['video_input'].get('destination', 'res00')
        self.first_vector_sent = False
        self.last_vector_time = time.time()  # Track when we last sent a vector
        
        # Print initial connection info
        dest_config = self.config['controllers'].get(self.destination)
        if dest_config:
            print("\nInitial controller connection info:")
            print(f"Destination: {self.destination}")
            print(f"IP: {dest_config['ip']}")
            print(f"Port: {dest_config.get('listen_port', 8765)}")
            print(f"URI: ws://{dest_config['ip']}:{dest_config.get('listen_port', 8765)}")
        else:
            print(f"\nWarning: No configuration found for {self.destination}")

        # Remove or set to False
        self.show_plots = False
        self.plots_initialized = False

    def load_config(self):
        """Load and initialize config with default ROI settings if needed"""
        config_path = Path(__file__).parent.parent.parent / 'config' / 'controllers.yaml'
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
        # Initialize video_input section if not present
        if 'video_input' not in config:
            config['video_input'] = {}
            
        # Initialize ROI configs if not present
        if 'roi_configs' not in config['video_input']:
            config['video_input']['roi_configs'] = {}
            
        # Ensure all ROIs have at least empty configs
        for i in range(1, 5):  # For ROIs 1-4
            roi_name = f'roi_{i}'
            if roi_name not in config['video_input']['roi_configs']:
                config['video_input']['roi_configs'][roi_name] = {
                    'x': 0,
                    'y': 0,
                    'width': 100,
                    'height': 100,
                    'description': f"ROI {i}",
                    'selected_cells': []
                }
                
        # Save initialized config
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
            
        return config

    def get_stream_url(self, stream_name: str = 'venice_live') -> Optional[str]:
        """Get stream URL from config"""
        if not self.config or 'streams' not in self.config:
            return None
        return self.config['streams'].get(stream_name, {}).get('url')
        
    def connect_to_stream(self, url: str) -> bool:
        """Connect to YouTube stream with retry logic"""
        for attempt in range(self.max_retries):
            try:
                print(f"Connection attempt {attempt + 1}/{self.max_retries}")
                
                # Configure yt-dlp
                ydl_opts = {
                    'format': 'best',
                    'quiet': True,
                }
                
                # Get stream URL using yt-dlp
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    stream_url = info['url']
                
                # Open video stream with timeout property
                self.cap = cv2.VideoCapture(stream_url)
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)  # Reduce buffer size
                if not self.cap.isOpened():
                    raise Exception("Could not open stream")
                
                self.is_running = True
                self.last_frame_success = time.time()
                print(f"Connected to stream: {info.get('title', 'Unknown')}")
                return True
                
            except Exception as e:
                print(f"Connection attempt {attempt + 1} failed: {e}")
                if self.cap:
                    self.cap.release()
                if attempt < self.max_retries - 1:
                    print(f"Retrying in {self.retry_delay} seconds...")
                    time.sleep(self.retry_delay)
                
        print("All connection attempts failed")
        return False
            
    def get_frame(self) -> Optional[np.ndarray]:
        """Get current frame from stream with timeout check"""
        if not self.is_running:
            return None
            
        try:
            # Check for stream timeout
            if time.time() - self.last_frame_success > self.stream_timeout:
                print("\nStream timeout detected, attempting to reconnect...")
                self.reconnect()
                return None
                
            ret, frame = self.cap.read()
            if ret:
                self.last_frame_success = time.time()
                self.last_frame = frame
                self.frame_count += 1
                return frame
            else:
                print("\nFailed to read frame, attempting to reconnect...")
                self.reconnect()
                return None
                
        except Exception as e:
            print(f"\nError reading frame: {e}")
            self.reconnect()
            return None
            
    def get_venice_time(self):
        """Get current time in Venice"""
        utc_now = datetime.now(pytz.UTC)
        return utc_now.astimezone(self.venice_tz)

    def encode_time(self, timestamp):
        """Encodes time-of-day into sin-cos representation using Venice time.
        
        Converts time to a point on a circle where:
        - 00:00:00 = 0 radians
        - 12:00:00 = π radians
        - 23:59:59 = 2π radians
        """
        # Convert to Venice time if timestamp is naive
        if timestamp.tzinfo is None:
            timestamp = datetime.now(self.venice_tz)
        else:
            timestamp = timestamp.astimezone(self.venice_tz)
            
        # Convert to decimal hours with seconds precision
        hour = timestamp.hour
        minute = timestamp.minute
        second = timestamp.second
        
        # Convert to fraction of day [0, 1]
        day_fraction = (hour + minute/60 + second/3600) / 24.0
        
        # Convert to radians [0, 2π]
        angle = 2 * np.pi * day_fraction
        
        # Calculate sine and cosine
        t_sin = np.sin(angle)
        t_cos = np.cos(angle)
        
        return t_sin, t_cos

    def calculate_movement_rate(self, roi_config):
        """Compute movement using Rate of Change Filtering"""
        if len(self.frame_buffer) < 3:
            return 0.0
            
        # Get ROI coordinates
        x = int(roi_config['x'])
        y = int(roi_config['y'])
        w = int(roi_config['width'])
        h = int(roi_config['height'])
        roi = (x, y, x+w, y+h)
        
        # Get frames from buffer
        frame1, frame2, frame3 = self.frame_buffer[-3:]
        
        # Convert to grayscale
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        gray3 = cv2.cvtColor(frame3, cv2.COLOR_BGR2GRAY)
        
        # Compute absolute differences
        diff1 = cv2.absdiff(gray1, gray2)
        diff2 = cv2.absdiff(gray2, gray3)
        
        # Compute rate of change
        rate_of_change = np.abs(diff2.astype(np.int16) - diff1.astype(np.int16))
        
        # Threshold: Ignore small intensity shifts
        rate_of_change[rate_of_change < self.movement_threshold] = 0
        
        # Focus on ROI
        roi_change = rate_of_change[y:y+h, x:x+w]
        
        # Compute movement score (percentage of significant changes)
        movement_score = np.sum(roi_change > 0) / (roi_change.shape[0] * roi_change.shape[1])
        
        # Scale to [20, 127] range
        scaled_score = 20 + (movement_score * (127 - 20))
        return np.clip(scaled_score, 20, 127)

    def init_plots(self):
        """Disabled in headless mode"""
        pass

    def update_plots(self):
        """Disabled in headless mode"""
        pass

    def process_frame(self, return_movements=False):
        """Process a single frame with error handling"""
        try:
            current_time = time.time()
            movements = {}
            
            # Check if it's time for a new frame
            if current_time - self.last_frame_time < self.frame_interval:
                return movements if return_movements else None
            
            ret, frame = self.cap.read()
            if not ret:
                raise ValueError("Failed to read frame")
            
            # Update frame buffer
            self.frame_buffer.append(frame.copy())
            if len(self.frame_buffer) > self.buffer_size:
                self.frame_buffer.pop(0)
            
            # Only calculate and save if we're in calculation mode
            if self.calculating:
                # Calculate movement for each ROI if we have enough frames
                if len(self.frame_buffer) == self.buffer_size:
                    for roi_name, roi_config in self.roi_configs.items():
                        movement = self.calculate_movement_rate(roi_config)
                        self.movement_buffers[roi_name].append(movement)
                        movements[roi_name] = movement
                
                # Check if it's time to calculate vectors (every vector_interval seconds)
                if current_time - self.last_vector_time >= self.vector_interval:
                    # This would be where vector calculation happens if needed
                    self.last_vector_time = current_time
                
                # Check if it's time to save to CSV (every save_interval seconds)
                if current_time - self.last_save_time >= self.save_interval:
                    # Flag that we need to save to CSV
                    self.save_needed = True
                    self.last_save_time = current_time
            else:
                # Clear movement buffers when stopping calculation
                if hasattr(self, 'movement_buffers'):
                    for roi_name in self.movement_buffers:
                        self.movement_buffers[roi_name] = []
                self.frame_buffer = []  # Clear frame buffer too
            
            self.last_frame_time = current_time
            self.current_movements = movements  # Store for display
            
            return movements if return_movements else None
            
        except Exception as e:
            print(f"\nError in frame processing: {e}")
            movements = {}
            self.reconnect()
            
        return movements if return_movements else None

    def get_csv_path(self):
        """Get CSV path with date-based rotation"""
        # Get base directory (supports both development and deployed environments)
        if os.path.exists('/home/input-column/venice/data'):
            # We're on the Raspberry Pi deployment
            base_dir = Path('/home/input-column/venice/data')
        else:
            # We're in development environment
            project_root = Path(__file__).parent.parent.parent
            base_dir = project_root / 'data'
        
        # Ensure data directory exists
        base_dir.mkdir(parents=True, exist_ok=True)
        
        # Get current Venice time and format date string
        venice_time = self.get_venice_time()
        date_str = venice_time.strftime('%Y%m%d')
        
        # Return full path with date
        return base_dir / f"movement_vectors_{date_str}.csv"

    async def check_and_save(self):
        """Check if save is needed and save to CSV only (not sending to controller)"""
        if self.save_needed and len(self.movement_buffers['roi_1']) >= 30:
            # Save to CSV, but don't send to controller
            success = await self.save_to_csv_only()
            self.save_needed = False
            return success
        return False
    
    async def save_to_csv_only(self):
        """Save movement vector to CSV only, without sending to controller"""
        if len(self.movement_buffers['roi_1']) >= 30:
            # Scale values for CSV - use the latest 30 values
            scaled_values = []
            # If we have more than 30 values, get the latest 30
            buffer_values = self.movement_buffers['roi_1'][-30:]
            
            for i in range(30):
                raw_movement = buffer_values[i]
                scaled = self.scale_movement_log(raw_movement, 0, 100)
                scaled_values.append(scaled)
            
            # Get current time in Venice
            venice_time = self.get_venice_time()
            t_sin, t_cos = self.encode_time(venice_time)
            
            # Get CSV file path and ensure parent directory exists
            csv_path = self.get_csv_path()
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"\nSaving data to CSV file: {csv_path}")
            
            # Write data to CSV
            try:
                # Create CSV if it doesn't exist, append if it does
                file_exists = csv_path.exists()
                with open(csv_path, mode='a', newline='') as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        # Write header if new file
                        writer.writerow(['timestamp', 't_sin', 't_cos'] + [f'movement_{i}' for i in range(30)])
                    
                    # Write data row
                    writer.writerow([str(venice_time), t_sin, t_cos] + scaled_values)
                print(f"Successfully wrote data to {csv_path}")
                return True
            except Exception as e:
                print(f"Error writing to CSV: {e}")
                return False
        else:
            print(f"Not enough values to save: {len(self.movement_buffers['roi_1'])}/30")
            return False
    
    async def send_movement_vector(self):
        """Send latest movement vector to controller"""
        # Only send if we're not waiting for an ACK and have enough values
        if len(self.movement_buffers['roi_1']) >= 30:
            # Scale values for transmission - always use the latest 30 values
            scaled_values = []
            # Get the latest 30 values
            buffer_values = self.movement_buffers['roi_1'][-30:]
            
            for i in range(30):
                raw_movement = buffer_values[i]
                scaled = self.scale_movement_log(raw_movement, 0, 100)
                scaled_values.append(scaled)
            
            # Get current time in Venice
            venice_time = self.get_venice_time()
            t_sin, t_cos = self.encode_time(venice_time)
            
            # Create data packet
            data = {
                'type': 'movement_data',
                'timestamp': str(venice_time),
                'data': {
                    'pot_values': scaled_values,
                    't_sin': t_sin,
                    't_cos': t_cos
                }
            }
            
            # Send to controller
            success = await self.send_to_controller(data)
            
            # We don't clear the buffer after sending, so new data will continue to accumulate
            # The next send will use the latest 30 values from the buffer
            
            return success
        else:
            print(f"Not enough values to send: {len(self.movement_buffers['roi_1'])}/30")
            return False

    async def save_movement_vector(self):
        """Legacy method - now just calls save_to_csv_only for backward compatibility"""
        return await self.save_to_csv_only()

    def run(self, stream_url):
        """Main processing loop"""
        self.connect_to_stream(stream_url)
        try:
            while True:
                self.process_frame()
                
        except KeyboardInterrupt:
            print("\nStopping video processing...")
        finally:
            if self.cap:
                self.cap.release()
            if self.show_plots:
                plt.close('all')
            cv2.destroyAllWindows()

    def show_frame(self, frame, window_name="Venice Stream"):
        """Show frame with ROI overlay and movement values"""
        if frame is not None:
            display_frame = frame.copy()
            
            # Add Venice timestamp and frame number
            venice_time = self.get_venice_time().strftime('%H:%M:%S')
            cv2.putText(display_frame, f"Frame: {self.frame_count} | Venice Time: {venice_time}", 
                      (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Draw ROIs if enabled
            if self.show_rois and self.roi_configs:
                for roi_name, roi_config in self.roi_configs.items():
                    x = int(roi_config['x'])
                    y = int(roi_config['y'])
                    w = int(roi_config['width'])
                    h = int(roi_config['height'])
                    cv2.rectangle(display_frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    
                    # Add ROI label and movement value if calculating
                    if hasattr(self, 'current_movements') and self.calculating:
                        movement_val = self.current_movements.get(roi_name, 0)
                        cv2.putText(display_frame, 
                                  f"{roi_name}: {movement_val:.2f}", 
                                  (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 
                                  0.6, (0, 255, 0), 2)
            
            # Draw recording indicator and time encoding when calculating
            if self.calculating:
                # Get current time encoding
                t_sin, t_cos = self.encode_time(self.get_venice_time())
                
                # Draw recording dot
                radius = 10
                center = (display_frame.shape[1]-20, 20)
                cv2.circle(display_frame, center, radius, (0, 0, 255), -1)
                
                # Add time encoding values
                cv2.putText(display_frame,
                          f"sin(t): {t_sin:.2f}",
                          (display_frame.shape[1]-150, 15),
                          cv2.FONT_HERSHEY_SIMPLEX,
                          0.5, (255, 255, 255), 1)
                cv2.putText(display_frame,
                          f"cos(t): {t_cos:.2f}",
                          (display_frame.shape[1]-150, 35),
                          cv2.FONT_HERSHEY_SIMPLEX,
                          0.5, (255, 255, 255), 1)
                
            cv2.imshow(window_name, display_frame)
        return True
            
    def close(self):
        """Clean up resources"""
        self.is_running = False
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()

    def save_roi_to_config(self, roi_number: int, selected_cells: list):
        """Save ROI coordinates from selected cells to config"""
        if not selected_cells:
            return False
            
        # Calculate ROI bounds from selected cells
        cell_coords = np.array(selected_cells) * self.cell_size
        min_x = np.min(cell_coords[:, 0])
        min_y = np.min(cell_coords[:, 1])
        max_x = np.max(cell_coords[:, 0]) + self.cell_size
        max_y = np.max(cell_coords[:, 1]) + self.cell_size
        
        # Update config
        roi_name = f'roi_{roi_number}'
        self.config['video_input']['roi_configs'][roi_name] = {
            'x': int(min_x),
            'y': int(min_y),
            'width': int(max_x - min_x),
            'height': int(max_y - min_y),
            'description': f"ROI {roi_number}",
            'selected_cells': selected_cells  # Store the original cell selections too
        }
        
        # Save to config file
        config_path = Path(__file__).parent.parent.parent / 'config' / 'controllers.yaml'
        print(f"Saving ROI {roi_number} to {config_path}")
        with open(config_path, 'w') as f:
            yaml.dump(self.config, f, default_flow_style=False)
            
        # Update roi_configs reference
        self.roi_configs = self.config['video_input']['roi_configs']
        return True

    def select_single_roi(self, frame):
        """Select a single ROI by number"""
        try:
            roi_num = int(input("\nEnter ROI number to edit (1-4) or 0 to cancel: "))
            if roi_num == 0:
                return False
            if 1 <= roi_num <= 4:
                print("\nClick cells to select, press ENTER when done, ESC to cancel")
                # Make sure we're using a copy of the frame
                frame_copy = frame.copy()
                selected_cells = self.select_roi(frame_copy)
                if selected_cells:
                    print(f"Saving ROI {roi_num} configuration...")
                    self.save_roi_to_config(roi_num, selected_cells)
                    return True
                else:
                    print(f"ROI {roi_num} selection cancelled")
                    return False
            else:
                print("Invalid ROI number. Please enter 1-4 or 0 to cancel.")
                return False
        except ValueError:
            print("Invalid input. Please enter a number.")
            return False
        except Exception as e:
            print(f"Error in ROI selection: {e}")
            return False

    def select_all_rois(self, frame):
        """Select all four ROIs using grid interface"""
        for roi_num in range(1, 5):
            print(f"\nSelecting ROI {roi_num} of 4")
            print("Click cells to select, press ENTER when done, ESC to cancel")
            
            selected_cells = self.select_roi(frame)
            if selected_cells:
                self.save_roi_to_config(roi_num, selected_cells)
            else:
                print(f"ROI {roi_num} selection cancelled")
                return False
        return True

    def select_roi(self, frame):
        """Select ROI using grid interface"""
        # Create a copy of the frame for drawing
        display = frame.copy()
        height, width = frame.shape[:2]
        
        # Calculate grid
        rows = height // self.cell_size
        cols = width // self.cell_size
        
        # Draw initial grid with thinner, darker lines
        grid_color = (50, 50, 50)  # Darker gray
        grid_thickness = 1  # Thinner lines
        
        # Draw grid
        for i in range(rows + 1):
            cv2.line(display, (0, i * self.cell_size), 
                    (width, i * self.cell_size), grid_color, grid_thickness)
        for j in range(cols + 1):
            cv2.line(display, (j * self.cell_size, 0), 
                    (j * self.cell_size, height), grid_color, grid_thickness)
        
        self.selected_cells = []  # Reset selected cells
        
        def mouse_callback(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                # Convert click to grid coordinates
                cell_x = x // self.cell_size
                cell_y = y // self.cell_size
                cell = [cell_x, cell_y]
                
                # Toggle cell selection
                if cell in self.selected_cells:
                    self.selected_cells.remove(cell)
                else:
                    self.selected_cells.append(cell)
                
                # Redraw grid and selections
                display_updated = frame.copy()
                
                # Draw grid with same style
                for i in range(rows + 1):
                    cv2.line(display_updated, (0, i * self.cell_size), 
                            (width, i * self.cell_size), grid_color, grid_thickness)
                for j in range(cols + 1):
                    cv2.line(display_updated, (j * self.cell_size, 0), 
                            (j * self.cell_size, height), grid_color, grid_thickness)
                
                # Draw selected cells
                for cell_x, cell_y in self.selected_cells:
                    x1 = cell_x * self.cell_size
                    y1 = cell_y * self.cell_size
                    cv2.rectangle(display_updated, 
                                (x1, y1), 
                                (x1 + self.cell_size, y1 + self.cell_size), 
                                (0, 255, 0), 2)
                
                cv2.imshow("Select ROI", display_updated)
        
        # Set up window and mouse callback
        cv2.namedWindow("Select ROI")
        cv2.setMouseCallback("Select ROI", mouse_callback)
        cv2.imshow("Select ROI", display)
        
        while True:
            key = cv2.waitKey(1) & 0xFF
            if key == 13:  # Enter key
                cv2.destroyWindow("Select ROI")
                return self.selected_cells
            elif key == 27:  # Escape key
                cv2.destroyWindow("Select ROI")
                return None

    def reconnect(self):
        """Attempt to reconnect to the stream"""
        print("Reconnecting to stream...")
        self.is_running = False
        if self.cap:
            self.cap.release()
            
        # Get the current stream URL
        url = self.get_stream_url('venice_live')
        if not url:
            print("ERROR: No stream URL found in config")
            return
            
        # Try to reconnect
        if self.connect_to_stream(url):
            print("Successfully reconnected")
        else:
            print("Failed to reconnect")

    def scale_movement_log(self, raw_movement, min_value, max_value):
        """Same scaling as builder uses"""
        try:
            if max_value <= min_value:
                return 20
            if raw_movement <= min_value:
                return 20
            if raw_movement >= max_value:
                return 127
                
            log_scaled = np.log1p(raw_movement - min_value) / np.log1p(max_value - min_value)
            scaled = int(round(20 + log_scaled * (127 - 20)))
            return max(20, min(127, scaled))
            
        except Exception as e:
            print(f"Error scaling movement value: {e}")
            return 20

    async def send_to_controller(self, data):
        """Send data to res00 controller"""
        try:
            # Get controller config
            dest_config = self.config['controllers'].get(self.destination)
            if not dest_config:
                print(f"No configuration found for destination: {self.destination}")
                return False

            # Connect to controller
            uri = f"ws://{dest_config['ip']}:{dest_config.get('listen_port', 8765)}"
            print(f"\nConnecting to {self.destination}:")
            print(f"URI: {uri}")
            
            async with websockets.connect(uri) as websocket:
                print(f"Connected to {self.destination}")
                await websocket.send(json.dumps(data))
                print(f"Data sent to {self.destination}:")
                print(json.dumps(data, indent=2))
                return True

        except Exception as e:
            print(f"Error sending to controller: {e}")
            return False

class VideoInputWithAck(VideoInput):
    def __init__(self):
        super().__init__()
        self.waiting_for_ack = False
        self.server = None
        self.listen_port = 8777  # Port to listen for acknowledgments
        self.last_message = None
        self.message_sent = False
        self.ack_destination = 'output'  # The controller that will send ACKs
        
        # Print ACK info
        output_config = self.config['controllers'].get(self.ack_destination)
        if output_config:
            print(f"\nWill receive acknowledgments from: {self.ack_destination}")
            print(f"On listen port: {self.listen_port}")
        else:
            print(f"\nWarning: No configuration found for ACK source: {self.ack_destination}")

if __name__ == "__main__":
    print("Please run tests/test_video_input.py for testing") 