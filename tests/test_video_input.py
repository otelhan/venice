import pytest
import cv2
import numpy as np
from src.networking.video_input import VideoInput
import time
import matplotlib
matplotlib.use('TkAgg')  # Use TkAgg backend for Mac compatibility

def test_video_input():
    """Test video input with a Venice live stream"""
    print("\nTesting video input with Venice live stream...")
    
    # Create video input
    video = VideoInput()
    
    # Get stream URL from config
    url = video.get_stream_url('venice_live')
    if not url:
        print("ERROR: No stream URL found in config")
        return
        
    print(f"Attempting to connect to: {url}")
    
    # Connect to stream
    assert video.connect_to_stream(url), "Failed to connect to stream"
    
    print("\nShowing stream for 30 seconds...")
    print("Press 'q' to quit early")
    
    print("\nControls:")
    print("'r' - Select new ROI (click cells to select, ENTER to confirm, ESC to cancel)")
    print("'c' - Show cropped ROI")
    print("'q' - Quit")
    
    start_time = time.time()
    frames = 0
    
    try:
        cv2.namedWindow("Venice Live", cv2.WINDOW_NORMAL)
        cv2.moveWindow("Venice Live", 0, 0)
        
        while time.time() - start_time < 30:
            frame = video.get_frame()
            if frame is not None:
                frames += 1
                video.show_frame(frame.copy(), "Venice Live")  # Use copy to prevent modifying original
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    video.select_roi()
                    # Force window focus back to main stream
                    cv2.namedWindow("Venice Live", cv2.WINDOW_NORMAL)
                    cv2.setWindowProperty("Venice Live", cv2.WND_PROP_TOPMOST, 1)
                elif key == ord('c'):
                    if video.roi:
                        roi_window = frame[video.roi['y']:video.roi['y']+video.roi['height'],
                                        video.roi['x']:video.roi['x']+video.roi['width']]
                        cv2.imshow("ROI", roi_window)
                
    finally:
        video.close()
        cv2.destroyAllWindows()  # Clean up windows
        
    fps = frames / (time.time() - start_time)
    print(f"\nProcessed {frames} frames at {fps:.1f} FPS")

if __name__ == "__main__":
    test_video_input() 