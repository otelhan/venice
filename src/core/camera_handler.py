import cv2  # type: ignore
import glob
import os
import numpy as np
import matplotlib.pyplot as plt
from threading import Lock

class CameraHandler:
    def __init__(self):
        self.camera = None
        self.window_name = "Live Camera Feed"
        self.frame_count = 0
        self.window_size = 100  # Show last 100 frames
        self.energy_values = []
        self.analyzer = None  # Will be initialized when we get first frame
        self.prev_frame = None
        self.plot_lock = Lock()  # Add thread safety
        
        # Setup energy plot
        plt.ion()
        self.fig, self.ax = plt.subplots(num='Energy Plot')
        self.line, = self.ax.plot([], [], 'b-', linewidth=2)
        self.ax.set_ylim(0, 8)  # Adjust for entropy values
        self.ax.set_xlabel('Frame Number')
        self.ax.set_ylabel('Energy (Entropy)')
        self.ax.grid(True)
        self.fig.show()
        
    def find_camera(self):
        """Find available video devices"""
        try:
            # Check common video device patterns
            video_devices = glob.glob('/dev/video*')  # Linux style
            if not video_devices:
                video_devices = glob.glob('/dev/avf*')  # macOS style
                
            if video_devices:
                print(f"Found video devices: {video_devices}")
                return 0  # OpenCV usually maps first device to 0
            return 0
        except:
            return 0
        
    def start_camera(self, camera_id=None):
        """Start the camera stream"""
        try:
            if camera_id is None:
                camera_id = self.find_camera()
                
            print(f"\nTrying to open camera {camera_id}")
            self.camera = cv2.VideoCapture(camera_id)
            
            if not self.camera.isOpened():
                print(f"Failed with camera {camera_id}, trying default camera")
                self.camera = cv2.VideoCapture(0)
                if not self.camera.isOpened():
                    raise ValueError("Could not open any camera")
                    
            print(f"\nCamera stream started on device {camera_id}")
            return True
            
        except Exception as e:
            print(f"\nERROR starting camera: {e}")
            return False
            
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
                
            # Update x-axis to show actual frame numbers
            start_frame = max(0, self.frame_count - self.window_size)
            xdata = range(start_frame, start_frame + len(self.energy_values))
            
            self.line.set_data(xdata, self.energy_values)
            self.ax.set_xlim(start_frame, start_frame + self.window_size)
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()
            
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
            small_frame = cv2.resize(frame, (width//2, height//2), 
                                   interpolation=cv2.INTER_NEAREST)
            gray_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
            
            # Calculate and plot energy
            energy = self.calculate_frame_energy(gray_frame)
            self.update_energy_plot(energy)
            
            # Show video frame
            cv2.imshow(self.window_name, gray_frame)
            cv2.setWindowProperty(self.window_name, cv2.WND_PROP_TOPMOST, 1)
            self.frame_count += 1
            
            return cv2.waitKey(1) & 0xFF != ord('q')
        return False
        
    def stop_camera(self):
        """Stop the camera stream and close windows"""
        if self.camera:
            self.camera.release()
            self.camera = None
        cv2.destroyAllWindows()
        print("\nCamera stream stopped")
        
    def __del__(self):
        """Cleanup"""
        self.stop_camera() 