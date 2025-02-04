import pytest
import cv2
import numpy as np
from src.networking.video_input import VideoInput
import time

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
    
    start_time = time.time()
    frames = 0
    
    try:
        while time.time() - start_time < 30:  # Run for 30 seconds
            frame = video.get_frame()
            if frame is not None:
                frames += 1
                if not video.show_frame(frame, "Venice Live"):
                    break
                
    finally:
        video.close()
        
    fps = frames / (time.time() - start_time)
    print(f"\nProcessed {frames} frames at {fps:.1f} FPS")

if __name__ == "__main__":
    test_video_input() 