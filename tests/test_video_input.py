import pytest
import cv2
import numpy as np
from src.networking.video_input import VideoInput
import time
import os
from pathlib import Path
import yaml
import argparse  # Add argument parsing
import asyncio

@pytest.fixture
def video_input():
    return VideoInput()

@pytest.fixture
def sample_frame():
    # Create a sample 800x600 frame
    return np.random.randint(0, 255, (600, 800, 3), dtype=np.uint8)

def test_init(video_input):
    """Test initialization"""
    assert video_input.is_running == False
    assert video_input.cap is None
    assert len(video_input.movement_buffers) == 4  # Changed from 3 to 4
    assert 'roi_1' in video_input.movement_buffers

def test_load_config(video_input):
    """Test config loading"""
    config = video_input.config
    assert 'video_input' in config
    assert 'roi_configs' in config['video_input']
    assert 'roi_1' in config['video_input']['roi_configs']

def test_calculate_movement(video_input, sample_frame):
    """Test movement calculation for a single ROI"""
    roi_config = video_input.roi_configs['roi_1']
    
    # First call should return 0 (no previous frame)
    movement1 = video_input.calculate_movement(sample_frame, roi_config)
    assert movement1 == 0
    
    # Second call should return non-zero (comparing with previous frame)
    movement2 = video_input.calculate_movement(sample_frame, roi_config)
    assert movement2 >= 0

def test_calculate_time_features(video_input):
    """Test time feature calculation"""
    t_sin, t_cos = video_input.calculate_time_features()
    
    # Check values are in correct range
    assert -1 <= t_sin <= 1
    assert -1 <= t_cos <= 1
    
    # Check they're not both 0
    assert not (t_sin == 0 and t_cos == 0)

def test_save_movement_vectors(video_input, tmp_path):
    """Test saving movement vectors to CSV"""
    # Modify config to use temporary path
    video_input.config['video_input']['output']['csv_path'] = str(tmp_path / "test_vectors.csv")
    
    # Add some test data to buffers
    for roi in video_input.movement_buffers:
        video_input.movement_buffers[roi] = list(range(30))  # 30 samples
        
    # Save vectors
    video_input.save_movement_vectors()
    
    # Check file exists and has correct format
    csv_path = Path(video_input.config['video_input']['output']['csv_path'])
    assert csv_path.exists()
    
    # Could add more specific checks for CSV content here

def test_show_frame(video_input, sample_frame):
    """Test frame display with ROI overlay"""
    result = video_input.show_frame(sample_frame)
    assert result == True
    cv2.destroyAllWindows()

def test_video_input(fullscreen=False):
    """Test video input with a Venice live stream"""
    print("\nTesting video input with Venice live stream...")
    print("\nControls:")
    print("'s' - Select all ROIs")
    print("'r' - Select single ROI")
    print("'t' - Toggle ROI display")
    print("'f' - Toggle fullscreen")
    print("'q' - Quit")
    
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
    
    try:
        # Set up window
        window_name = "Venice Stream"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        if fullscreen:
            cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        
        print("\nStarting calculations automatically...")
        video.calculating = True  # Auto-start calculations
        video.last_vector_time = 0  # Reset the last vector time to ensure immediate saving
        
        frame_count = 0
        last_save_time = time.time()
        
        while True:
            frame = video.get_frame()
            if frame is not None:
                frame_count += 1
                
                # Process frame (always calculating)
                try:
                    movements = video.process_frame(return_movements=True)
                    if movements:
                        print(f"\rFrame {frame_count} | Movements: {movements}", end="", flush=True)
                        
                        # Force a save check every 30 seconds
                        current_time = time.time()
                        if current_time - last_save_time >= 30.0:
                            if len(video.movement_buffers['roi_1']) >= 30:
                                # Use asyncio.create_task to handle the coroutine
                                asyncio.create_task(video.save_movement_vector())
                                last_save_time = current_time
                                print(f"\nSaved movement vector at {video.get_venice_time()}")
                            
                except Exception as e:
                    print(f"\nError in processing: {e}")
                
                # Show frame
                video.show_frame(frame.copy(), window_name)
                
                # Check for commands
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    print("\nQuitting...")
                    break
                elif key == ord('r'):
                    print("\nStarting ROI selection...")
                    video.select_single_roi(frame)
                elif key == ord('s'):
                    print("\nStarting all ROIs selection...")
                    video.select_all_rois(frame)
                elif key == ord('t'):
                    video.show_rois = not video.show_rois
                    print(f"\nROI display: {'On' if video.show_rois else 'Off'}")
                elif key == ord('f'):  # Add fullscreen toggle
                    fullscreen = not fullscreen
                    if fullscreen:
                        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                    else:
                        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
                    print(f"\nFullscreen: {'On' if fullscreen else 'Off'}")
                
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    finally:
        video.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Video Input Test')
    parser.add_argument('--fullscreen', action='store_true', help='Start in fullscreen mode')
    args = parser.parse_args()
    
    test_video_input(fullscreen=args.fullscreen) 