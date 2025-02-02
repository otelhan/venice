import cv2  # type: ignore
import numpy as np  # type: ignore
import matplotlib.pyplot as plt  # type: ignore
from matplotlib.animation import FuncAnimation  # type: ignore

class VideoProcessor:
    def __init__(self):
        self.video = None
        self.roi = None
        self.movements = []
        self.times = []
        self.frame_count = 0
        self.window_size = 1000
        
        # Initialize plot variables as None
        self.fig = None
        self.ax = None
        self.line = None
        
    def __del__(self):
        """Cleanup when object is destroyed"""
        if self.video is not None:
            self.video.release()
        cv2.destroyAllWindows()
        plt.close('all')  # Only close plots when object is destroyed
        
    def setup_plot(self):
        """Setup the movement plot when needed"""
        # Close any existing movement plot first
        if self.fig is not None:
            plt.close('Video Movement Plot')
            self.fig = None
            self.ax = None
            self.line = None
            
        plt.ion()
        self.fig = plt.figure('Video Movement Plot')
        self.ax = self.fig.add_subplot(111)
        self.line, = self.ax.plot([], [], 'b-')
        self.ax.set_title('Movement Over Time')
        self.ax.set_xlabel('Frame Number')
        self.ax.set_ylabel('Movement Score')
        self.ax.set_ylim(0, 50)  # Fixed y-axis scale
        self.ax.grid(True)
        
    def update_plot(self):
        """Update the plot with new movement data"""
        # Keep only the last window_size frames
        if len(self.times) > self.window_size:
            start_idx = len(self.times) - self.window_size
            plot_times = [t - self.times[start_idx] for t in self.times[start_idx:]]
            plot_movements = self.movements[start_idx:]
        else:
            plot_times = self.times
            plot_movements = self.movements
            
        self.line.set_data(plot_times, plot_movements)
        self.ax.set_xlim(0, self.window_size)  # Fixed x-axis scale
        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()
        
    def load_video(self, video_path):
        """Load a video file"""
        # Release previous video if it exists
        if self.video is not None:
            self.video.release()
            
        self.video = cv2.VideoCapture(video_path)
        if not self.video.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")
            
    def select_roi(self):
        """Select ROI and reset video to start"""
        # Read first frame
        ret, frame = self.video.read()
        if not ret:
            print("Could not read frame for ROI selection")
            return False
            
        # Select ROI
        self.roi = cv2.selectROI("Select Region", frame, fromCenter=False, showCrosshair=True)
        cv2.destroyWindow("Select Region")
        
        # Reset video to start
        self.video.set(cv2.CAP_PROP_POS_FRAMES, 0)
        return True
        
    def calculate_movement(self, max_frames=None, show_plot=False):
        """Calculate movement in ROI"""
        if self.roi is None:
            print("No ROI selected")
            return None
            
        movements = []
        frame_count = 0
        prev_frame = None
        
        # Only setup plot if requested
        if show_plot:
            self.setup_plot()
        
        while True:
            ret, frame = self.video.read()
            if not ret or (max_frames and frame_count >= max_frames):
                break
                
            # Create a black frame
            black_frame = np.zeros_like(frame)
            
            # Extract and show ROI
            x, y, w, h = self.roi
            roi_frame = frame[int(y):int(y+h), int(x):int(x+w)]
            
            # Place ROI on black frame
            black_frame[int(y):int(y+h), int(x):int(x+w)] = roi_frame
            
            # Show the frame with only ROI visible
            cv2.imshow("ROI", black_frame)
            
            if prev_frame is not None:
                # Calculate absolute difference between frames
                diff = cv2.absdiff(roi_frame, prev_frame)
                
                # Convert to grayscale if needed
                if len(diff.shape) == 3:
                    diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
                
                # Calculate movement score
                movement = np.sum(diff) / (diff.shape[0] * diff.shape[1])
                movements.append(movement)
                print(f"Movement: {movement:.2f}", end='\r')
                
                # Update plot only if enabled
                if show_plot:
                    self.times.append(frame_count)
                    self.movements = movements  # Update stored movements
                    self.update_plot()
            
            prev_frame = roi_frame.copy()
            frame_count += 1
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
        # Reset video position
        self.video.set(cv2.CAP_PROP_POS_FRAMES, 0)
        cv2.destroyAllWindows()
        return movements

def test_video_processor():
    """Test function to demonstrate usage"""
    processor = VideoProcessor()
    
    # Load video
    #processor.load_video("input_videos/leone_hotel_afternoon.mp4")
    processor.load_video("input_videos/Ponte delle Guglie_night.mp4")
    
    # Let user select ROI
    processor.select_roi()
    
    # Calculate movement
    movements = processor.calculate_movement()
    
    # Print results
    print(f"\nDetected {len(movements)} movement measurements")
    print(f"Average movement: {np.mean(movements):.2f}")
    print(f"Max movement: {np.max(movements):.2f}")

if __name__ == "__main__":
    test_video_processor() 