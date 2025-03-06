import cv2  # type: ignore
import glob
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Use Agg backend for headless operation
import matplotlib.pyplot as plt
from threading import Lock
import time

class CameraHandler:
    def __init__(self):
        self.camera = None
        self.is_running = False
        self.camera_index = 0  # Default camera
        self.has_display = True  # Force display since we're running locally
        if not self._init_camera():
            print("WARNING: Failed to initialize camera")
        self.window_name = "Live Camera Feed"
        self.frame_count = 0
        self.window_size = 100  # Show last 100 frames
        self.energy_values = []
        self.analyzer = None  # Will be initialized when we get first frame
        self.prev_frame = None
        self.plot_lock = Lock()  # Add thread safety
        
        # Setup energy plot for local display
        plt.ion()  # Interactive mode
        self.fig, self.ax = plt.subplots(figsize=(8, 4))
        self.line, = self.ax.plot([], [], 'b-', linewidth=2)
        self.ax.set_ylim(0, 8)  # Adjust for entropy values
        self.ax.set_xlabel('Frame Number')
        self.ax.set_ylabel('Energy (Entropy)')
        self.ax.grid(True)
        self.fig.canvas.manager.window.attributes('-topmost', 1)  # Keep window on top
        plt.show()  # Show the window
        
    def _init_camera(self):
        """Initialize and test camera connection"""
        try:
            # Try to open camera
            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                print("ERROR: Could not open camera")
                return False
                
            # Camera works, release it (we'll reopen when needed)
            cap.release()
            print("Camera initialized successfully")
            return True
            
        except Exception as e:
            print(f"Error initializing camera: {e}")
            return False
            
    def start_camera(self):
        """Start the camera"""
        if self.is_running:
            return True
            
        try:
            self.camera = cv2.VideoCapture(self.camera_index)
            if not self.camera.isOpened():
                print("ERROR: Could not start camera")
                return False
                
            self.is_running = True
            print("Camera started")
            return True
            
        except Exception as e:
            print(f"Error starting camera: {e}")
            return False
            
    def stop_camera(self):
        """Stop the camera"""
        if self.camera and self.is_running:
            self.camera.release()
            self.is_running = False
            print("Camera stopped")
            
    def get_frame(self):
        """Get a frame from the camera"""
        if not self.is_running:
            if not self.start_camera():
                return None
                
        try:
            ret, frame = self.camera.read()
            if not ret:
                print("ERROR: Could not read frame")
                return None
            return frame
            
        except Exception as e:
            print(f"Error reading frame: {e}")
            return None
            
    def init_analyzer(self, frame_shape):
        """Initialize the optimized analyzer with frame shape"""
        h, w = frame_shape
        Y, X = np.ogrid[:h:2, :w:2]  # Subsampled
        center_y, center_x = h//4, w//4  # Adjusted for subsampling
        mask = 0.3 + 0.7 * np.exp(-((X - center_x)**2 + (Y - center_y)**2) / (h*w/32))
        self.analyzer_mask = mask.astype(np.float32)  # Lower precision is fine
        
    def calculate_frame_energy(self, frame):
        """Calculate frame energy using entropy"""
        # Calculate histogram
        histogram = cv2.calcHist([frame], [0], None, [256], [0, 256])
        
        # Normalize histogram to get probabilities
        histogram = histogram.ravel() / histogram.sum()
        
        # Calculate entropy only for non-zero probabilities
        non_zero = histogram > 0
        entropy = -np.sum(histogram[non_zero] * np.log2(histogram[non_zero]))
        
        return entropy
        
    def update_energy_plot(self, energy):
        """Update the energy plot with thread safety"""
        with self.plot_lock:
            self.energy_values.append(energy)
            if len(self.energy_values) > self.window_size:
                self.energy_values = self.energy_values[-self.window_size:]
                
            if self.has_display and self.line is not None:
                start_frame = max(0, self.frame_count - self.window_size)
                xdata = range(start_frame, start_frame + len(self.energy_values))
                self.line.set_data(xdata, self.energy_values)
                self.ax.set_xlim(start_frame, start_frame + self.window_size)
                self.fig.canvas.draw_idle()
                self.fig.canvas.flush_events()
            else:
                # Print energy values for headless operation
                print(f"Frame {self.frame_count}: Energy = {energy:.2f}")
            
    def draw_energy_plot(self, frame, energy):
        """Draw energy plot directly on the frame"""
        # Add energy to history with sliding window
        self.energy_values.append(energy)
        if len(self.energy_values) > self.window_size:
            self.energy_values = self.energy_values[-self.window_size:]
            
        # Define plot area dimensions to match bottom third of frame
        PLOT_HEIGHT = frame.shape[0] // 3
        PLOT_WIDTH = frame.shape[1] - 40
        PLOT_X = 20
        PLOT_Y = frame.shape[0] - PLOT_HEIGHT - 10
        
        # Draw grid lines and y-axis labels
        for i in range(6):
            y = PLOT_Y + PLOT_HEIGHT - (i * PLOT_HEIGHT // 5)
            cv2.line(frame, (PLOT_X, y), 
                    (PLOT_X + PLOT_WIDTH, y), 
                    (128, 128, 128), 1)
            label = str(i * 10)
            cv2.putText(frame, label, (PLOT_X - 25, y + 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        
        # Draw x-axis labels (frame numbers)
        start_frame = max(0, self.frame_count - self.window_size)
        for i in range(0, self.window_size + 1, 20):
            x = PLOT_X + (i * PLOT_WIDTH // self.window_size)
            cv2.line(frame, (x, PLOT_Y + PLOT_HEIGHT), 
                    (x, PLOT_Y + PLOT_HEIGHT - 5), 
                    (128, 128, 128), 1)
            # Show actual frame numbers
            label = str(start_frame + i)
            cv2.putText(frame, label, (x - 10, PLOT_Y + PLOT_HEIGHT + 15), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        
        # Draw energy values with proper x-axis scaling
        if len(self.energy_values) > 1:
            points = []
            for i, e in enumerate(self.energy_values):
                # Scale x position based on actual position in window
                x = PLOT_X + (i * PLOT_WIDTH // self.window_size)
                y = PLOT_Y + PLOT_HEIGHT - int((e * PLOT_HEIGHT) / 50)
                points.append((x, y))
            
            # Draw the line connecting points
            for i in range(len(points)-1):
                cv2.line(frame, points[i], points[i+1], (255, 255, 255), 1)
        
        return frame
        
    def show_frame(self):
        """Show camera feed and update energy plot"""
        if not self.camera:
            return False
            
        ret, frame = self.camera.read()
        if ret:
            # Scale down and process frame
            height, width = frame.shape[:2]
            small_frame = cv2.resize(frame, (width//2, height//2))
            gray_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            
            # Calculate and plot energy
            energy = self.calculate_frame_energy(gray_frame)
            self.update_energy_plot(energy)
            
            # Show video frame in separate window
            cv2.imshow(self.window_name, gray_frame)
            cv2.moveWindow(self.window_name, 0, 0)  # Position window
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_TOPMOST, 1)
            self.frame_count += 1
            
            # Update plot
            plt.pause(0.001)  # Allow plot to update
            
            return cv2.waitKey(1) & 0xFF != ord('q')
        return False
        
    def __del__(self):
        """Cleanup when object is destroyed"""
        self.stop_camera() 