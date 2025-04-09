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
import threading
import queue

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

        # Network operation flag to avoid blocking main thread
        self.network_busy = False
        
        # Create frame queue for threaded processing
        self.frame_queue = queue.Queue(maxsize=10)  # Limit queue size to 10 frames
        self.processing_thread = None
        
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
        """Connect to video source (either local file or YouTube stream)"""
        for attempt in range(self.max_retries):
            try:
                print(f"Connection attempt {attempt + 1}/{self.max_retries}")
                
                # Store the current source for reference
                self.current_source = url
                
                # Check if the input is a local file
                if os.path.isfile(url):
                    print(f"Opening local video file: {url}")
                    self.cap = cv2.VideoCapture(url)
                else:
                    print(f"Attempting to connect to stream: {url}")
                    # Configure yt-dlp
                    ydl_opts = {
                        'format': 'best',
                        'quiet': True,
                    }
                    
                    # Get stream URL using yt-dlp
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        stream_url = info['url']
                    
                    # Open video stream
                    self.cap = cv2.VideoCapture(stream_url)
                
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)  # Reduce buffer size
                self.cap.set(cv2.CAP_PROP_FPS, 30)  # Request 30fps
                
                if not self.cap.isOpened():
                    raise Exception("Could not open video source")
                
                self.is_running = True
                self.last_frame_success = time.time()
                
                # Start frame capture thread
                self.start_frame_capture_thread()
                
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
    
    def start_frame_capture_thread(self):
        """Start a background thread to continuously capture frames"""
        def capture_frames():
            while self.is_running:
                if not self.cap or not self.cap.isOpened():
                    time.sleep(0.1)
                    continue
                
                success, frame = self.cap.read()
                if success:
                    self.last_frame_success = time.time()
                    # Only add to queue if there's space (to avoid memory issues)
                    if not self.frame_queue.full():
                        self.frame_queue.put(frame)
                    time.sleep(0.01)  # Small sleep to avoid hogging CPU
                else:
                    # Check if this is a local file
                    if hasattr(self, 'current_source') and os.path.isfile(self.current_source):
                        print("\nEnd of video file reached, restarting...")
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Reset to beginning
                    else:
                        print("\nFailed to read frame in capture thread")
                        self.reconnect()
                        time.sleep(0.5)
        
        # Start the capture thread
        self.processing_thread = threading.Thread(target=capture_frames, daemon=True)
        self.processing_thread.start()
        print("Frame capture thread started")
            
    def get_frame(self) -> Optional[np.ndarray]:
        """Get current frame from queue with timeout check"""
        if not self.is_running:
            return None
            
        try:
            # Check for stream timeout
            if time.time() - self.last_frame_success > self.stream_timeout:
                print("\nStream timeout detected, attempting to reconnect...")
                self.reconnect()
                return None
                
            # Try to get a frame from the queue with a short timeout
            try:
                frame = self.frame_queue.get(timeout=0.1)
                self.frame_count += 1
                self.last_frame = frame
                return frame
            except queue.Empty:
                # If no frame is available, return the last frame if we have one
                return self.last_frame
                
        except Exception as e:
            print(f"\nError getting frame: {e}")
            return None
            
    def get_venice_time(self):
        """Get current time in Venice timezone"""
        utc_now = datetime.now(pytz.utc)
        venice_now = utc_now.astimezone(self.venice_tz)
        return venice_now

    def encode_time(self, timestamp):
        """
        Encode time of day (hours, minutes, seconds) into sin/cos values
        Returns: (sin_value, cos_value) tuple
        """
        # Get hours as float (0.0-23.999)
        hours = timestamp.hour
        minutes = timestamp.minute
        seconds = timestamp.second
        microseconds = timestamp.microsecond
        
        # Convert to fraction of day (0.0-1.0)
        day_fraction = (hours + minutes/60 + seconds/3600 + microseconds/3600000000) / 24.0
        
        # Convert to radians (0 to 2π)
        angle_rad = day_fraction * 2 * np.pi
        
        # Calculate sin and cos values
        sin_val = np.sin(angle_rad)
        cos_val = np.cos(angle_rad)
        
        return sin_val, cos_val

    def calculate_movement_rate(self, roi_config):
        """Calculate movement rate for an ROI"""
        if len(self.frame_buffer) < self.buffer_size:
            return 0.0
            
        try:
            # Extract ROI from newest and oldest frames
            oldest = self.frame_buffer[0]
            newest = self.frame_buffer[-1]
            
            x = int(roi_config['x'])
            y = int(roi_config['y'])
            w = int(roi_config['width'])
            h = int(roi_config['height'])
            
            oldest_roi = oldest[y:y+h, x:x+w]
            newest_roi = newest[y:y+h, x:x+w]
            
            # Convert to grayscale and apply blur to reduce noise
            oldest_gray = cv2.cvtColor(oldest_roi, cv2.COLOR_BGR2GRAY)
            newest_gray = cv2.cvtColor(newest_roi, cv2.COLOR_BGR2GRAY)
            
            oldest_blur = cv2.GaussianBlur(oldest_gray, (21, 21), 0)
            newest_blur = cv2.GaussianBlur(newest_gray, (21, 21), 0)
            
            # Calculate absolute difference between frames
            frame_diff = cv2.absdiff(oldest_blur, newest_blur)
            
            # Apply threshold to highlight changes
            _, thresh = cv2.threshold(frame_diff, self.movement_threshold, 255, cv2.THRESH_BINARY)
            
            # Count changed pixels (white pixels in threshold image)
            movement_pixels = cv2.countNonZero(thresh)
            
            # Normalize by ROI size to get percentage of changed pixels
            roi_size = w * h
            movement_rate = (movement_pixels / roi_size) * 100.0
            
            return movement_rate
            
        except Exception as e:
            print(f"Error calculating movement: {e}")
            return 0.0

    def process_frame(self, return_movements=False):
        """Process a single frame with error handling"""
        try:
            current_time = time.time()
            movements = {}
            
            # Check if it's time for a new frame
            if current_time - self.last_frame_time < self.frame_interval:
                return movements if return_movements else None
            
            # Get frame from buffer or capture
            frame = self.last_frame
            if frame is None:
                return movements if return_movements else None
            
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
                        
                        # Limit buffer size to prevent unbounded growth
                        max_buffer_size = 100  # Keep last 100 values maximum
                        if len(self.movement_buffers[roi_name]) > max_buffer_size:
                            # Remove oldest values, keeping the most recent
                            self.movement_buffers[roi_name] = self.movement_buffers[roi_name][-max_buffer_size:]
                
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
            print(f"\n[ERROR] Error in frame processing: {e}")
            movements = {}
            
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
            print(f"\n[STATUS] Save interval reached, saving data to CSV...")
            success = await self.save_to_csv_only()
            self.save_needed = False
            return success
        elif self.save_needed:
            print(f"[WARNING] Save interval reached but not enough data ({len(self.movement_buffers['roi_1'])}/30)")
            # Reset the flag anyway to avoid repeated warnings
            self.save_needed = False
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
                scaled = self.scale_movement_log(raw_movement, 20, 127)  # Update range to 20-127
                scaled_values.append(scaled)
            
            # Get current time in Venice
            venice_time = self.get_venice_time()
            t_sin, t_cos = self.encode_time(venice_time)
            
            # Get CSV file path and ensure parent directory exists
            csv_path = self.get_csv_path()
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"\n[CSV] Saving data to file: {csv_path}")
            
            # Create a thread for CSV writing to avoid blocking
            def write_csv():
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
                    print(f"[CSV] Successfully wrote data to {csv_path}")
                except Exception as e:
                    print(f"[ERROR] Failed to write to CSV: {e}")
            
            # Create and start CSV write thread
            csv_thread = threading.Thread(target=write_csv)
            csv_thread.daemon = True
            csv_thread.start()
            return True
        else:
            print(f"[WARNING] Not enough values to save to CSV: {len(self.movement_buffers['roi_1'])}/30")
            return False
    
    async def wait_for_ack_task(self):
        """Non-blocking task to wait for acknowledgment with timeout"""
        try:
            print("\n[ACK] Started acknowledgment wait task")
            self.waiting_for_ack = True
            
            # Reset the event before waiting
            self.ack_received.clear()
            
            print(f"[ACK] Waiting for acknowledgment (timeout: {self.ack_timeout}s)")
            
            # Create a timeout task that will automatically clear the wait after timeout
            async def timeout_task():
                try:
                    # Wait for the specified timeout period
                    await asyncio.sleep(self.ack_timeout)
                    
                    # If we're still waiting, cancel the wait
                    if self.waiting_for_ack:
                        print(f"\n[WARNING] Acknowledgment timeout after {self.ack_timeout} seconds")
                        self.waiting_for_ack = False
                except asyncio.CancelledError:
                    # Task was cancelled, which means ack was received
                    pass
                except Exception as e:
                    print(f"[ERROR] Error in timeout task: {e}")
            
            # Start the timeout task in the background
            self.ack_task = asyncio.create_task(timeout_task())
            
            # Return immediately - don't block execution
            # The timeout task will handle clearing the wait flag after timeout
            return True
            
        except Exception as e:
            print(f"[ERROR] Error in acknowledgment wait task: {e}")
            self.waiting_for_ack = False
            return False
            
    async def cancel_ack_wait(self):
        """Cancel the current acknowledgment wait task if it exists"""
        if self.ack_task and not self.ack_task.done():
            self.ack_task.cancel()
            try:
                await self.ack_task
            except asyncio.CancelledError:
                pass
            self.waiting_for_ack = False
            print("[ACK] Acknowledgment wait cancelled")
    
    async def send_movement_vector(self):
        """Send latest movement vector with acknowledgment wait"""
        # Only send if not currently waiting for an ACK and have enough values
        if self.waiting_for_ack:
            print("\n[ACK] Still waiting for acknowledgment, skipping send")
            return False
            
        if self.network_busy:
            print("\n[NETWORK] Network operation in progress, skipping send")
            return False
            
        if len(self.movement_buffers['roi_1']) >= 30:
            # Set network busy flag to prevent concurrent operations
            self.network_busy = True
            
            try:
                # Scale values for transmission - always use the latest 30 values
                scaled_values = []
                buffer_values = self.movement_buffers['roi_1'][-30:]
                
                for i in range(30):
                    raw_movement = buffer_values[i]
                    # Use updated scaling to ensure values are in 20-127 range
                    scaled = self.scale_movement_log(raw_movement, 20, 127)
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
                
                if success:
                    print("\n[ACK] Message sent, starting acknowledgment wait task")
                    # Cancel any existing ack task
                    await self.cancel_ack_wait()
                    # Start non-blocking ack wait task
                    await self.wait_for_ack_task()
                    
                return success
            
            finally:
                # Reset network busy flag
                self.network_busy = False
        else:
            print(f"[WARNING] Not enough values to send: {len(self.movement_buffers['roi_1'])}/30")
            return False
    
    async def send_to_controller(self, data):
        """Send data to controller with improved error handling"""
        try:
            # Get controller config
            dest_config = self.config['controllers'].get(self.destination)
            if not dest_config:
                print(f"\n[ERROR] No configuration found for destination: {self.destination}")
                return False

            # Connect to controller with a shorter timeout
            uri = f"ws://{dest_config['ip']}:{dest_config.get('listen_port', 8765)}"
            print(f"\n[STATUS] Connecting to {self.destination}:")
            print(f"URI: {uri}")
            
            # Use a timeout to prevent hanging connection - shorter timeout
            try:
                async with asyncio.timeout(3):  # 3 seconds timeout instead of 5
                    async with websockets.connect(
                        uri,
                        ping_interval=None,  # Disable ping to reduce traffic
                        ping_timeout=None,
                        close_timeout=1.0  # Quick closure
                    ) as websocket:
                        print(f"[SUCCESS] Connected to {self.destination}")
                        await websocket.send(json.dumps(data))
                        print(f"[SUCCESS] Data sent to {self.destination}")
                        if len(data.get('data', {}).get('pot_values', [])) > 0:
                            timestamp = data.get('timestamp', 'unknown')
                            pot_count = len(data.get('data', {}).get('pot_values', []))
                            print(f"[DATA] Timestamp: {timestamp}")
                            print(f"[DATA] Sent {pot_count} movement values")
                        return True
            except asyncio.TimeoutError:
                print(f"\n[ERROR] Connection to {self.destination} timed out")
                return False
                    
        except websockets.exceptions.InvalidStatusCode as e:
            print(f"\n[ERROR] Invalid status from {self.destination}: {e}")
            return False
        except websockets.exceptions.ConnectionClosed as e:
            print(f"\n[ERROR] Connection to {self.destination} closed unexpectedly: {e}")
            return False
        except Exception as e:
            print(f"\n[ERROR] Failed to send to controller: {e}")
            return False

    def reconnect(self):
        """Reconnect to stream if connection is lost"""
        if not self.is_running:
            return
            
        print("\n[INFO] Attempting to reconnect to stream...")
        
        # Stop the current stream
        self.is_running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        
        # Wait for processing thread to exit
        if self.processing_thread and self.processing_thread.is_alive():
            print("[INFO] Waiting for processing thread to complete...")
            time.sleep(1)  # Give thread a chance to exit
            
        # Clear frame queue
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except:
                pass
        
        # Reconnect to stream
        url = self.get_stream_url('venice_live')
        if url:
            print(f"[INFO] Reconnecting to {url}...")
            self.is_running = True
            self.connect_to_stream(url)
        else:
            print("[ERROR] No stream URL found for reconnection")

    def scale_movement_log(self, raw_movement, min_value, max_value):
        """Scale movement value using logarithmic scaling (to emphasize smaller movements)"""
        # Apply a logarithmic scaling to emphasize smaller movements
        if raw_movement <= 0:
            return 20  # Return minimum valid value for output (20 instead of 0)
            
        # Log scaling (natural log) with a small offset to handle zero
        log_value = np.log(raw_movement + 0.1)
        
        # Map to final range 20-127 instead of min_value-max_value
        # Empirically, log(0.1) ≈ -2.3 and maximum log for large movement could be around 4.6
        scaled = 20 + (log_value + 2.3) * ((127 - 20) / 7)
        
        # Clamp to range 20-127
        return max(20, min(127, scaled))

    def close(self):
        """Clean up resources"""
        print("\n[INFO] Closing video input...")
        self.is_running = False
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        
        # Wait for threads to exit
        if self.processing_thread and self.processing_thread.is_alive():
            print("[INFO] Waiting for processing thread to complete...")
            time.sleep(1)  # Give thread a chance to exit
        
        print("[INFO] Video input closed")

    def show_frame(self, frame, window_name="Venice Stream"):
        """Show frame with ROI overlay and movement values"""
        if frame is not None:
            # Create a black background the size of the screen
            screen_width = cv2.getWindowImageRect(window_name)[2]
            screen_height = cv2.getWindowImageRect(window_name)[3]
            
            # Only create background if window is initialized
            if screen_width > 0 and screen_height > 0:
                # Create black background
                background = np.zeros((screen_height, screen_width, 3), dtype=np.uint8)
                
                # Calculate position to center the frame
                frame_height, frame_width = frame.shape[:2]
                x_offset = (screen_width - frame_width) // 2
                y_offset = (screen_height - frame_height) // 2
                
                # Create a copy of the frame for overlay
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
                
                # Place the frame on the black background
                if x_offset >= 0 and y_offset >= 0:
                    background[y_offset:y_offset+frame_height, x_offset:x_offset+frame_width] = display_frame
                    cv2.imshow(window_name, background)
                else:
                    # If window is smaller than frame, just show the frame
                    cv2.imshow(window_name, display_frame)
            else:
                # If window is not yet initialized, show the frame directly
                cv2.imshow(window_name, frame)
        return True

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

class VideoInputWithAck(VideoInput):
    def __init__(self):
        super().__init__()
        self.waiting_for_ack = False
        self.server = None
        self.listen_port = 8777  # Port to listen for acknowledgments
        self.last_message = None
        self.message_sent = False
        self.ack_destination = 'output'  # The controller that will send ACKs
        
        # Async tasks
        self.ack_task = None
        self.ack_received = asyncio.Event()
        self.ack_timeout = 30  # Reduced timeout for acknowledgments in seconds
        
        # Print ACK info
        output_config = self.config['controllers'].get(self.ack_destination)
        if output_config:
            print(f"\nWill receive acknowledgments from: {self.ack_destination}")
            print(f"On listen port: {self.listen_port}")
            print(f"ACK timeout: {self.ack_timeout} seconds")
        else:
            print(f"\nWarning: No configuration found for ACK source: {self.ack_destination}")
    
    async def setup_ack_server(self, force_restart=False):
        """Setup websocket server to listen for acknowledgments"""
        try:
            # Handle force restart
            if force_restart and self.server:
                print("[ACK] Force restarting acknowledgment server")
                self.server.close()
                await self.server.wait_closed()
                self.server = None
                
            # Only set up the server once, unless force_restart is True
            if self.server is not None:
                print(f"[ACK] Acknowledgment server already running on port {self.listen_port}")
                # Check if the server is still valid
                if hasattr(self.server, 'sockets') and self.server.sockets:
                    print("[ACK] Reusing existing server")
                    return self.server
                else:
                    print("[ACK] Existing server appears invalid, creating new server")
                    self.server = None
            
            # Check if the port is already in use by another process
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', self.listen_port))
                sock.close()
                
                if result == 0:
                    print(f"[WARNING] Port {self.listen_port} is already in use by another process")
                    print("[ACK] Attempting to use existing port binding...")
            except Exception as e:
                print(f"[WARNING] Error checking port availability: {e}")
            
            # Now try to create the server
            print(f"\n[ACK] Setting up acknowledgment server on port {self.listen_port}")
                
            # Websocket handler for incoming messages
            async def handler(websocket):
                try:
                    client_ip = websocket.remote_address[0] if hasattr(websocket, 'remote_address') else 'unknown'
                    print(f"[ACK] New connection established from {client_ip}")
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            print(f"\n[ACK] Received message: {data}")
                            
                            # Check if it's an acknowledgment
                            if data.get('type') == 'ack':
                                print(f"[ACK] Acknowledgment received from {client_ip}!")
                                # Important: Set this BEFORE setting the event
                                self.waiting_for_ack = False
                                
                                # Clear any timeouts and set the event
                                if self.ack_task and not self.ack_task.done():
                                    self.ack_task.cancel()
                                    
                                self.ack_received.set()
                                
                                # Respond with confirmation (optional but helps debugging)
                                try:
                                    response = {
                                        'type': 'ack_receipt',
                                        'status': 'success',
                                        'message': 'Acknowledgment received successfully'
                                    }
                                    await websocket.send(json.dumps(response))
                                except:
                                    pass
                            else:
                                print(f"[INFO] Received non-ACK message: {data.get('type', 'unknown')}")
                                
                        except json.JSONDecodeError:
                            print(f"[WARNING] Received invalid JSON: {message}")
                except websockets.exceptions.ConnectionClosed:
                    print(f"[INFO] ACK connection from {client_ip} closed gracefully")
                except Exception as e:
                    print(f"[ERROR] Websocket handler error: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Create the server with more lenient settings
            print(f"[ACK] Starting server on 0.0.0.0:{self.listen_port}")
            
            try:
                # Get the websockets version to determine the correct function signature
                import websockets
                ws_version = websockets.__version__.split('.')
                major_version = int(ws_version[0]) if ws_version else 0
                
                # Try with increased retry count and exception handling
                max_retries = 3
                retry_delay = 2  # seconds
                last_error = None
                
                for attempt in range(max_retries):
                    try:
                        # Add a small delay between retries
                        if attempt > 0:
                            print(f"[ACK] Retry attempt {attempt}/{max_retries} after {retry_delay} seconds")
                            await asyncio.sleep(retry_delay)
                            
                        # Handle both older (path parameter required) and newer versions
                        if major_version >= 10:
                            # Newer websockets version (10.0+) - no path parameter
                            print(f"[INFO] Using websockets {websockets.__version__} (new API)")
                            # Try with SO_REUSEADDR option
                            self.server = await websockets.serve(
                                handler, 
                                "0.0.0.0",
                                self.listen_port,
                                ping_interval=None,
                                ping_timeout=None,
                                close_timeout=10,
                                max_size=10485760,
                                max_queue=32,
                                reuse_address=True  # Allow reuse of address
                            )
                        else:
                            # Older websockets version - path parameter required
                            print(f"[INFO] Using websockets {websockets.__version__} (legacy API)")
                            
                            # Create a wrapper handler that accepts the path parameter
                            async def legacy_handler(websocket, path):
                                await handler(websocket)
                                
                            self.server = await websockets.serve(
                                legacy_handler, 
                                "0.0.0.0",
                                self.listen_port,
                                ping_interval=None,
                                ping_timeout=None,
                                close_timeout=10,
                                max_size=10485760,
                                max_queue=32,
                                reuse_address=True  # Allow reuse of address
                            )
                        
                        # If we get here, server creation was successful
                        break
                    except OSError as e:
                        if e.errno == 98:  # Address already in use
                            print(f"[WARNING] Port {self.listen_port} is still in use (attempt {attempt+1}/{max_retries})")
                            # Try alternate port
                            alt_port = self.listen_port + attempt + 1
                            print(f"[ACK] Trying alternate port {alt_port}")
                            try:
                                if major_version >= 10:
                                    self.server = await websockets.serve(
                                        handler, 
                                        "0.0.0.0",
                                        alt_port,
                                        ping_interval=None,
                                        ping_timeout=None,
                                        close_timeout=10,
                                        max_size=10485760,
                                        max_queue=32
                                    )
                                else:
                                    self.server = await websockets.serve(
                                        legacy_handler, 
                                        "0.0.0.0",
                                        alt_port,
                                        ping_interval=None,
                                        ping_timeout=None,
                                        close_timeout=10,
                                        max_size=10485760,
                                        max_queue=32
                                    )
                                # Update the port if successful
                                self.listen_port = alt_port
                                print(f"[ACK] Successfully bound to alternate port {alt_port}")
                                break
                            except Exception as alt_err:
                                print(f"[ERROR] Failed to bind to alternate port: {alt_err}")
                        last_error = e
                    except Exception as e:
                        print(f"[ERROR] Server creation error: {e}")
                        last_error = e
                
                # Check if all attempts failed
                if self.server is None:
                    if last_error:
                        print(f"[ERROR] All server creation attempts failed: {last_error}")
                    else:
                        print("[ERROR] All server creation attempts failed with unknown error")
                    return None
                
                if self.server:
                    print(f"[ACK] Acknowledgment server is running on port {self.listen_port}")
                    if hasattr(self.server, 'sockets') and self.server.sockets:
                        for sock in self.server.sockets:
                            print(f"[ACK] Socket: {sock}")
                    else:
                        print("[WARNING] Server has no sockets!")
                else:
                    print("[ERROR] Failed to create server!")
                    return None
            except Exception as e:
                print(f"[ERROR] Failed to create server: {e}")
                import traceback
                traceback.print_exc()
                return None
            
            # Determine our IP address - try multiple methods
            ip = await self.get_reliable_ip()
            
            # Add our listen port to the config so the output knows where to send ACKs
            if 'video_input' not in self.config:
                self.config['video_input'] = {}
            
            # Set our IP and port in the config
            self.config['video_input']['listen_port'] = self.listen_port
            self.config['video_input']['ip'] = ip
            
            print(f"[ACK] IP address set in config: {ip}:{self.listen_port}")
            
            # Save the config
            config_path = Path(__file__).parent.parent.parent / 'config' / 'controllers.yaml'
            with open(config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False)
                print(f"[ACK] Updated config saved to {config_path}")
            
            # Verify the server is actually running
            server_ok = self.verify_server()
            if not server_ok:
                print("[WARNING] Server verification failed!")
            
            # We need to keep this task running
            return self.server
            
        except Exception as e:
            print(f"[ERROR] Failed to setup acknowledgment server: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def verify_server(self):
        """Verify the server is actually running"""
        if not self.server:
            print("[ERROR] No server object!")
            return False

        if not hasattr(self.server, 'sockets') or not self.server.sockets:
            print("[ERROR] Server has no sockets!")
            return False
            
        print(f"[ACK] Server verification successful - {len(self.server.sockets)} socket(s)")
        return True

    async def get_reliable_ip(self):
        """Get a reliable IP address using multiple methods"""
        ip = None
        
        # Method 1: Connect to external service
        try:
            ip = self.get_local_ip()
            print(f"[ACK] Method 1 IP: {ip}")
        except Exception as e:
            print(f"[WARNING] Method 1 IP detection failed: {e}")
        
        # Method 2: Use socket to get all interfaces
        if not ip or ip == '127.0.0.1':
            try:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(('10.255.255.255', 1))
                ip = s.getsockname()[0]
                s.close()
                print(f"[ACK] Method 2 IP: {ip}")
            except Exception as e:
                print(f"[WARNING] Method 2 IP detection failed: {e}")
        
        # Method 3: List all network interfaces
        if not ip or ip == '127.0.0.1':
            try:
                import socket
                import netifaces
                
                print("[ACK] Available network interfaces:")
                for interface in netifaces.interfaces():
                    try:
                        # Get IPv4 addresses
                        addrs = netifaces.ifaddresses(interface)
                        if netifaces.AF_INET in addrs:
                            for addr in addrs[netifaces.AF_INET]:
                                if 'addr' in addr and addr['addr'] != '127.0.0.1':
                                    print(f"  - {interface}: {addr['addr']}")
                                    # Use first non-loopback address
                                    if not ip or ip == '127.0.0.1':
                                        ip = addr['addr']
                                        print(f"[ACK] Method 3 IP: {ip} (from {interface})")
                    except Exception as e:
                        print(f"  - Error with {interface}: {e}")
            except ImportError:
                print("[WARNING] netifaces module not available")
            except Exception as e:
                print(f"[WARNING] Method 3 IP detection failed: {e}")
        
        # If all methods fail, use fallback
        if not ip:
            print("[WARNING] All IP detection methods failed. Using 0.0.0.0 (accept all)")
            ip = "0.0.0.0"
        else:
            print(f"[ACK] Final IP address selection: {ip}")
            
        return ip
            
    def get_local_ip(self):
        """Get the local IP address of this machine"""
        import socket
        try:
            # Connect to an external site to determine our outgoing IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Doesn't actually connect, just resolves route
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception as e:
            print(f"[WARNING] Could not determine local IP: {e}")
            # Try to get hostname IP
            try:
                hostname = socket.gethostname()
                local_ip = socket.gethostbyname(hostname)
                if local_ip != "127.0.0.1":
                    return local_ip
            except:
                pass
            # Fallback to localhost
            return "127.0.0.1"

if __name__ == "__main__":
    print("Please run tests/test_video_input.py for testing") 