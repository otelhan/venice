import cv2
import numpy as np

class VideoProcessorSimulator:
    def __init__(self):
        self.video = None
        self.roi = None
        self.prev_frame = None
        self.selected_cells = []  # Add this to store selected cells
        
    def load_video(self, video_path):
        """Load video file"""
        self.video = cv2.VideoCapture(video_path)
        if not self.video.isOpened():
            print(f"Error: Could not open video {video_path}")
            return False
        return True
        
    def select_roi(self, default_roi=None):
        """Let user select ROI using a grid-based approach"""
        ret, frame = self.video.read()
        if not ret:
            return False
            
        # Create a copy for drawing
        grid_frame = frame.copy()
        height, width = frame.shape[:2]
        
        # Grid parameters
        cell_size = 40
        rows = height // cell_size
        cols = width // cell_size
        
        # Initialize selected cells
        self.selected_cells = []  # Reset selected cells
        
        # Load default ROI if provided
        if default_roi and 'selected_cells' in default_roi:
            self.selected_cells = default_roi['selected_cells']
            print("Default ROI loaded. Click to modify cells, press Enter when done.")
        elif default_roi and 'roi' in default_roi:
            x, y, w, h = default_roi['roi']
            start_cell_x = x // cell_size
            start_cell_y = y // cell_size
            end_cell_x = (x + w) // cell_size
            end_cell_y = (y + h) // cell_size
            
            for cx in range(start_cell_x, end_cell_x + 1):
                for cy in range(start_cell_y, end_cell_y + 1):
                    self.selected_cells.append((cx, cy))
            print("Default ROI converted. Click to modify cells, press Enter when done.")
        
        # Destroy any existing windows first
        cv2.destroyAllWindows()
        
        WINDOW_NAME = "Select ROI (Click cells, press Enter when done)"
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_TOPMOST, 1)  # Keep window on top
        
        def draw_grid():
            grid_frame = frame.copy()
            
            # Create overlay for grid lines
            grid_overlay = grid_frame.copy()
            for i in range(rows + 1):
                y = i * cell_size
                cv2.line(grid_overlay, (0, y), (width, y), (200, 200, 200), 1)
            for j in range(cols + 1):
                x = j * cell_size
                cv2.line(grid_overlay, (x, 0), (x, height), (200, 200, 200), 1)
            
            # Apply 50% opacity for grid lines
            cv2.addWeighted(grid_overlay, 0.5, grid_frame, 0.5, 0, grid_frame)
            
            # Fill selected cells
            cell_overlay = grid_frame.copy()
            for cell in self.selected_cells:
                x, y = cell
                pt1 = (x * cell_size, y * cell_size)
                pt2 = ((x + 1) * cell_size, (y + 1) * cell_size)
                cv2.rectangle(cell_overlay, pt1, pt2, (0, 255, 0), -1)
            
            # Apply transparency for selected cells
            cv2.addWeighted(cell_overlay, 0.3, grid_frame, 0.7, 0, grid_frame)
            
            # Add instruction text with better visibility
            cv2.putText(grid_frame, "Click to add/remove cells, Enter to confirm", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3)  # Black outline
            cv2.putText(grid_frame, "Click to add/remove cells, Enter to confirm", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)  # White text
            
            return grid_frame
        
        def mouse_callback(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                cell_x = x // cell_size
                cell_y = y // cell_size
                cell = (cell_x, cell_y)
                
                if cell not in self.selected_cells:
                    self.selected_cells.append(cell)
                else:
                    self.selected_cells.remove(cell)
                
                # Redraw and force window update
                updated_frame = draw_grid()
                cv2.imshow(WINDOW_NAME, updated_frame)
                cv2.waitKey(1)
        
        # Setup window and mouse callback
        cv2.imshow(WINDOW_NAME, draw_grid())
        cv2.setMouseCallback(WINDOW_NAME, mouse_callback)
        
        # Wait for user input
        while True:
            key = cv2.waitKey(1) & 0xFF
            if key == 13:  # Enter key
                break
            elif key == 27:  # Escape key
                self.selected_cells = []
                break
            
            # Redraw window to ensure it stays responsive
            cv2.imshow(WINDOW_NAME, draw_grid())
        
        cv2.destroyWindow(WINDOW_NAME)
        
        if not self.selected_cells:
            return False
            
        # Convert selected cells to ROI
        min_x = min(cell[0] for cell in self.selected_cells) * cell_size
        min_y = min(cell[1] for cell in self.selected_cells) * cell_size
        max_x = (max(cell[0] for cell in self.selected_cells) + 1) * cell_size
        max_y = (max(cell[1] for cell in self.selected_cells) + 1) * cell_size
        
        self.roi = (min_x, min_y, max_x - min_x, max_y - min_y)
        self.video.set(cv2.CAP_PROP_POS_FRAMES, 0)
        return True
        
    def calculate_movement(self, max_frames=300, start_frame=0):
        """Calculate movement in ROI for specified number of frames"""
        if not self.video or not self.roi:
            print("Error: Video or ROI not initialized")
            return None
            
        # Set video position to start_frame
        self.video.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        
        movements = []
        frame_count = 0
        self.prev_frame = None
        
        # Create window for video display
        cv2.namedWindow("Video", cv2.WINDOW_NORMAL)
        
        while frame_count < max_frames:
            ret, frame = self.video.read()
            if not ret:
                print(f"End of video reached at frame {start_frame + frame_count}")
                break
                
            try:
                # Extract ROI
                x, y, w, h = self.roi
                roi_frame = frame[int(y):int(y+h), int(x):int(x+w)]
                gray_roi = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2GRAY)
                
                # Draw ROI rectangle on frame
                cv2.rectangle(frame, (int(x), int(y)), (int(x+w), int(y+h)), (0, 255, 0), 2)
                
                # Add ROI coordinates text
                coord_text = f"x:{int(x)}, y:{int(y)}"
                cv2.putText(frame, coord_text, (int(x), int(y-10)), 
                          cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
                # Show frame
                cv2.imshow("Video", frame)
                
                if self.prev_frame is not None:
                    # Calculate movement score
                    diff = cv2.absdiff(gray_roi, self.prev_frame)
                    score = np.sum(diff) / (diff.shape[0] * diff.shape[1])
                    movements.append(score)
                    
                self.prev_frame = gray_roi.copy()
                frame_count += 1
                
                # Check for 'q' key to quit
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    print("Video playback stopped by user")
                    cv2.destroyWindow("Video")
                    return None
                
            except Exception as e:
                print(f"Error processing frame {start_frame + frame_count}: {e}")
                break
        
        cv2.destroyWindow("Video")
        print(f"Processed {len(movements)} frames")
        
        if len(movements) > 0:
            return movements
        return None
        
    def __del__(self):
        """Cleanup when object is destroyed"""
        if self.video is not None:
            self.video.release()
        cv2.destroyAllWindows() 