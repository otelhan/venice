import cv2
import numpy as np
from typing import Optional, Dict, Tuple
import time
import yt_dlp
import yaml
import os

class VideoInput:
    def __init__(self):
        self.stream = None
        self.cap = None
        self.frame_count = 0
        self.last_frame = None
        self.is_running = False
        self.config = self._load_config()
        self.roi = self._load_roi('venice_live')
        self.selected_cells = []
        self.cell_size = 40
        self.scale_factor = 1.0  # Add scale factor tracking
        
    def _load_config(self):
        """Load stream configuration"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                 'config', 'controllers.yaml')
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return None
            
    def get_stream_url(self, stream_name: str = 'venice_live') -> Optional[str]:
        """Get stream URL from config"""
        if not self.config or 'streams' not in self.config:
            return None
        return self.config['streams'].get(stream_name, {}).get('url')
        
    def connect_to_stream(self, url: str) -> bool:
        """Connect to YouTube stream"""
        try:
            print(f"Connecting to: {url}")
            
            # Configure yt-dlp
            ydl_opts = {
                'format': 'best',  # Get best quality
                'quiet': True,     # Reduce output
            }
            
            # Get stream URL using yt-dlp
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info['url']
                
            # Open video stream
            self.cap = cv2.VideoCapture(stream_url)
            if not self.cap.isOpened():
                print("ERROR: Could not open stream")
                return False
                
            self.is_running = True
            print(f"Connected to stream: {info.get('title', 'Unknown')}")
            return True
            
        except Exception as e:
            print(f"Error connecting to stream: {e}")
            return False
            
    def get_frame(self) -> Optional[np.ndarray]:
        """Get current frame from stream"""
        if not self.is_running:
            return None
            
        try:
            ret, frame = self.cap.read()
            if ret:
                self.last_frame = frame
                self.frame_count += 1
                return frame
            return None
            
        except Exception as e:
            print(f"Error reading frame: {e}")
            return None
            
    def _load_roi(self, stream_name: str) -> Dict:
        """Load ROI from config"""
        try:
            if not self.config or 'streams' not in self.config:
                return {'x': 0, 'y': 0, 'width': 0, 'height': 0}
            
            stream_config = self.config['streams'].get(stream_name, {})
            roi_config = stream_config.get('roi', {})
            
            if not roi_config:
                return {'x': 0, 'y': 0, 'width': 0, 'height': 0}
            
            # Get coordinates
            coordinates = roi_config.get('coordinates', {})
            roi = {
                'x': coordinates.get('x', 0),
                'y': coordinates.get('y', 0),
                'width': coordinates.get('width', 0),
                'height': coordinates.get('height', 0)
            }
            
            # Convert selected cells from lists to tuples
            if 'selected_cells' in roi_config:
                roi['selected_cells'] = [tuple(cell) for cell in roi_config['selected_cells']]
            
            return roi
            
        except Exception as e:
            print(f"Error loading ROI: {e}")
            return {'x': 0, 'y': 0, 'width': 0, 'height': 0}
        
    def _save_roi(self, stream_name: str, roi: Dict):
        """Save ROI to config file"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 
                                'config', 'controllers.yaml')
        try:
            # Convert tuples to lists for YAML storage
            roi_data = roi.copy()
            roi_data['selected_cells'] = [[x, y] for x, y in roi['selected_cells']]
            
            self.config['streams'][stream_name]['roi'] = roi_data
            with open(config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False)
        except Exception as e:
            print(f"Error saving ROI: {e}")
            
    def select_roi(self):
        """Select ROI using grid-based approach"""
        frame = self.get_frame()
        if frame is None:
            return False
        
        # Create a copy for drawing
        grid_frame = frame.copy()
        height, width = frame.shape[:2]
        
        # Grid parameters
        self.cell_size = 40
        rows = height // self.cell_size
        cols = width // self.cell_size
        
        # Initialize selected cells
        self.selected_cells = []
        
        # Flag to track if we're in ROI selection mode
        self.selecting_roi = True
        
        def draw_grid():
            grid_frame = frame.copy()
            
            # Create overlay for grid lines
            grid_overlay = grid_frame.copy()
            for i in range(rows + 1):
                y = i * self.cell_size
                cv2.line(grid_overlay, (0, y), (width, y), (200, 200, 200), 1)
            for j in range(cols + 1):
                x = j * self.cell_size
                cv2.line(grid_overlay, (x, 0), (x, height), (200, 200, 200), 1)
            
            # Apply 50% opacity for grid lines
            cv2.addWeighted(grid_overlay, 0.5, grid_frame, 0.5, 0, grid_frame)
            
            # Fill selected cells
            cell_overlay = grid_frame.copy()
            for cell in self.selected_cells:
                x, y = cell
                pt1 = (x * self.cell_size, y * self.cell_size)
                pt2 = ((x + 1) * self.cell_size, (y + 1) * self.cell_size)
                cv2.rectangle(cell_overlay, pt1, pt2, (0, 255, 0), -1)
            
            # Apply transparency for selected cells
            cv2.addWeighted(cell_overlay, 0.3, grid_frame, 0.7, 0, grid_frame)
            
            if self.selecting_roi:
                # Add instruction text with better visibility
                cv2.putText(grid_frame, "Click to add/remove cells, Enter when done", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3)
                cv2.putText(grid_frame, "Click to add/remove cells, Enter when done", 
                           (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
            
            return grid_frame
            
        def mouse_callback(event, x, y, flags, param):
            if self.selecting_roi and event == cv2.EVENT_LBUTTONDOWN:
                cell_x = x // self.cell_size
                cell_y = y // self.cell_size
                cell = (cell_x, cell_y)
                
                if cell not in self.selected_cells:
                    self.selected_cells.append(cell)
                else:
                    self.selected_cells.remove(cell)
                
                # Update grid on live stream window
                cv2.imshow("Live Stream", draw_grid())
        
        # Show initial grid
        cv2.imshow("Live Stream", draw_grid())
        cv2.setMouseCallback("Live Stream", mouse_callback)
        
        # Wait for user input
        while self.selecting_roi:
            key = cv2.waitKey(1) & 0xFF
            if key == 13:  # Enter key
                self.selecting_roi = False
                break
            elif key == 27:  # Escape key
                self.selected_cells = []
                self.selecting_roi = False
                break
        
        if not self.selected_cells:
            return False
        
        # Convert selected cells to ROI
        min_x = min(cell[0] for cell in self.selected_cells) * self.cell_size
        min_y = min(cell[1] for cell in self.selected_cells) * self.cell_size
        max_x = (max(cell[0] for cell in self.selected_cells) + 1) * self.cell_size
        max_y = (max(cell[1] for cell in self.selected_cells) + 1) * self.cell_size
        
        self.roi = {
            'x': min_x,
            'y': min_y,
            'width': max_x - min_x,
            'height': max_y - min_y
        }
        
        return True

    def show_frame(self, frame, window_name="Live Stream"):
        """Show frame with ROI overlay"""
        if frame is not None:
            # Draw ROI if it exists
            if hasattr(self, 'roi'):
                x = int(self.roi['x'])
                y = int(self.roi['y'])
                w = int(self.roi['width'])
                h = int(self.roi['height'])
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                
            cv2.imshow(window_name, frame)
        return True
            
    def close(self):
        """Clean up resources"""
        self.is_running = False
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows() 