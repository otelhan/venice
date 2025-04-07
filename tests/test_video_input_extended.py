import asyncio
import websockets
import json
import cv2
import numpy as np
import time
import os
from pathlib import Path
import yaml
import sys
import argparse
import threading
import queue
import traceback
from datetime import datetime

# Add project root to path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from src.networking.video_input import VideoInput, VideoInputWithAck

async def test_video_input(fullscreen=False, debug=False):
    """Test the video input module"""
    print("\nInitializing VideoInputWithAck...")
    # Create video input with ACK
    video_input = VideoInputWithAck()
    
    # Give WebSocket threads a moment to initialize
    print("Waiting for WebSocket threads to initialize...")
    time.sleep(2)
    
    # Create a window - always start in normal mode
    cv2.namedWindow('Video', cv2.WINDOW_NORMAL)
    
    # Get stream URL and connect
    stream_url = video_input.get_stream_url("venice_live")
    if not stream_url:
        print("No stream URL found in config")
        sys.exit(1)
    
    print(f"Attempting to connect to: {stream_url}")
    
    if not video_input.connect_to_stream(stream_url):
        print("Failed to connect to stream")
        sys.exit(1)
        
    # Setup CSV saving
    video_input.setup_csv_saving()
    
    # Add frame buffer for processing if it doesn't exist
    if not hasattr(video_input, 'frame_buffer'):
        video_input.frame_buffer = []
    
    # Add attribute for ROI selection if it doesn't exist    
    if not hasattr(video_input, 'selecting_roi'):
        video_input.selecting_roi = False
    
    # Add current movements attribute if it doesn't exist
    if not hasattr(video_input, 'current_movements'):
        video_input.current_movements = {}
    
    # Start frame processing
    video_input.calculating = True  # Start calculations automatically
    print("\nStarting calculations automatically...")
    
    frame_count = 0
    wait_count = 0
    yellow_color = (0, 190, 246)  # BGR value for RGB(246,190,0)
    green_color = (0, 255, 0)     # BGR value for green
    
    # Flag to track if we've sent our first data packet
    first_send_done = False
    
    # Main loop
    try:
        while True:
            # Get the next frame
            frame = video_input.get_frame()
            if frame is None:
                # If no frame, sleep a bit to avoid spinning
                time.sleep(0.1)
                continue
                
            # Process the frame
            try:
                # Add frame to buffer
                if len(video_input.frame_buffer) < video_input.buffer_size:
                    video_input.frame_buffer.append(frame.copy())
                    # Only print buffer status while filling up initially
                    print(f"Frame buffer: {len(video_input.frame_buffer)}/{video_input.buffer_size}")
                else:
                    # Shift buffer and add new frame
                    video_input.frame_buffer.pop(0)
                    video_input.frame_buffer.append(frame.copy())
                    # Only print buffer status every 30 frames
                    if frame_count % 30 == 0 and debug:
                        print(f"Processing frames: {frame_count}")
                
                # Update ROIs
                video_input.update_rois(frame)
                
                # Check for movement in ROIs if we have enough frames
                if len(video_input.frame_buffer) >= video_input.buffer_size:
                    video_input.check_for_movement()
                
                # Check if we need to save data
                if time.time() - video_input.last_save_time >= video_input.save_interval:
                    print("\n[STATUS] Save interval reached, saving data to CSV...")
                    video_input.save_to_csv()
                
                # Send data when we have 30 frames and no pending ACK
                # First time: send as soon as we reach 30 frames
                # After that: wait for ACK before sending again
                if len(video_input.movement_buffers['roi_1']) >= 30:
                    if (not first_send_done) or (not video_input.waiting_for_ack and first_send_done):
                        print("\n[STATUS] Sending movement data to controller...")
                        send_result = video_input.check_and_try_send()
                        if send_result:
                            first_send_done = True
                            print("[STATUS] First data packet sent successfully")
                
                # Process key presses for UI
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    # Toggle ROI selection mode
                    video_input.selecting_roi = not video_input.selecting_roi
                    print(f"\n[UI] ROI selection mode: {'on' if video_input.selecting_roi else 'off'}")
                elif key == ord('t'):
                    # Toggle ROI display
                    video_input.show_rois = not video_input.show_rois
                    print(f"\n[UI] ROI display: {'on' if video_input.show_rois else 'off'}")
                elif key == ord('f'):
                    # Toggle fullscreen
                    if cv2.getWindowProperty('Video', cv2.WND_PROP_FULLSCREEN) == cv2.WINDOW_FULLSCREEN:
                        cv2.setWindowProperty('Video', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
                    else:
                        cv2.setWindowProperty('Video', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                
                # Create a copy of the frame for drawing status
                display_frame = frame.copy()
                
                # Ensure show_rois is enabled
                video_input.show_rois = True
                
                # Draw ROIs on the display frame
                if video_input.show_rois and video_input.roi_configs:
                    for roi_name, roi_config in video_input.roi_configs.items():
                        x = int(roi_config['x'])
                        y = int(roi_config['y'])
                        w = int(roi_config['width'])
                        h = int(roi_config['height'])
                        cv2.rectangle(display_frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                        
                        # Add ROI label and movement value if available
                        if hasattr(video_input, 'current_movements'):
                            movement_val = video_input.current_movements.get(roi_name, 0)
                            cv2.putText(display_frame, 
                                      f"{roi_name}: {movement_val:.2f}", 
                                      (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 
                                      0.6, (0, 255, 0), 2)
                
                # Add frame count and Venice time
                frame_count += 1
                venice_time = datetime.now(video_input.venice_tz).strftime('%H:%M:%S')
                cv2.putText(display_frame, f"Frame: {frame_count} | Venice: {venice_time}", 
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
                # Add status messages
                status_y = 80  # Starting Y position for status messages
                
                # Main status message
                status_msg = "READY"
                status_color = green_color
                
                if video_input.waiting_for_ack:
                    status_msg = "WAITING FOR ACK"
                    status_color = yellow_color
                    wait_count += 1
                
                cv2.putText(display_frame, status_msg, (10, status_y), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)
                
                # Show the frame
                cv2.imshow('Video', display_frame)
                
            except Exception as e:
                print(f"\n[ERROR] Error processing frame: {e}")
                traceback.print_exc()
                time.sleep(0.5)  # Wait a bit before trying again
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        # Clean up
        video_input.cleanup()
        cv2.destroyAllWindows()

def main():
    parser = argparse.ArgumentParser(description='Test video input module.')
    parser.add_argument('--fullscreen', action='store_true', help='Start in fullscreen mode')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    args = parser.parse_args()
    
    # Run the test
    asyncio.run(test_video_input(fullscreen=args.fullscreen, debug=args.debug))

if __name__ == "__main__":
    main() 