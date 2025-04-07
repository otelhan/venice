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

# Add project root to path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from src.networking.video_input import VideoInputWithAck

async def test_video_input(fullscreen=False, debug=False):
    """Test video input with a Venice live stream"""
    print("\nTesting video input with Venice live stream...")
    print("\nControls:")
    print("'s' - Select all ROIs")
    print("'r' - Select single ROI")
    print("'t' - Toggle ROI display")
    print("'f' - Toggle fullscreen")
    print("'q' - Quit")
    
    # Create video input with acknowledgment handling
    video = VideoInputWithAck()
    
    # Start acknowledgment server and wait for it to be ready
    print("\nStarting acknowledgment server...")
    server_task = asyncio.create_task(video.setup_ack_server())
    
    # Give the server time to start up fully before connecting to stream
    await asyncio.sleep(2)
    print("Acknowledgment server started, listening on port 8777")
    
    # Get stream URL from config
    url = video.get_stream_url('venice_live')
    if not url:
        print("ERROR: No stream URL found in config")
        return
        
    print(f"Attempting to connect to: {url}")
    
    # Connect to stream
    assert video.connect_to_stream(url), "Failed to connect to stream"
    
    try:
        # Test CSV file path and directory access
        csv_path = video.get_csv_path()
        print(f"\nCSV file will be saved to: {csv_path}")
        print(f"Directory exists: {csv_path.parent.exists()}")
        print(f"Directory is writable: {os.access(str(csv_path.parent), os.W_OK)}")
        
        # Set up window
        window_name = "Venice Stream"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        if fullscreen:
            cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        
        print("\nStarting calculations automatically...")
        video.calculating = True  # Auto-start calculations
        video.last_vector_time = 0  # Reset the last vector time to ensure immediate vector calculation
        video.last_save_time = 0    # Reset the last save time to ensure immediate saving
        
        frame_count = 0
        initial_send = True  # Flag to send first data
        ack_wait_count = 0  # Counter for limiting ack wait messages
        
        while True:
            frame = video.get_frame()
            if frame is not None:
                frame_count += 1
                
                # Process frame (always calculating)
                try:
                    movements = video.process_frame(return_movements=True)
                    if movements:
                        # Only print frame-by-frame data in debug mode
                        if debug:
                            print(f"\rFrame {frame_count} | Movements: {movements}", end="", flush=True)
                        
                        # Check and save to CSV if needed (based on save_interval)
                        save_performed = await video.check_and_save()
                        if save_performed:
                            print(f"\nSaved to CSV at {video.get_venice_time()}")
                        
                        # Initial data send or periodic checks for sending data
                        if initial_send and len(video.movement_buffers['roi_1']) >= 30:
                            print("\n[INIT] Sending initial data packet...")
                            initial_send = False
                            await video.send_movement_vector()
                        elif not video.waiting_for_ack and len(video.movement_buffers['roi_1']) >= 30:
                            # Only try to send if not waiting for ack and we have enough data
                            await video.send_movement_vector()
                        elif video.waiting_for_ack:
                            # Print status message every 30 frames (to avoid flooding terminal)
                            ack_wait_count += 1
                            if ack_wait_count % 30 == 0:
                                print(f"\n[STATUS] Still waiting for acknowledgment...")
                        
                except Exception as e:
                    print(f"\nError in processing: {e}")
                
                # Show frame with status message
                frame_copy = frame.copy()
                
                # Add status messages with position
                y_pos = 80  # Start position from top
                
                # Connection status
                status_text = ""
                color = (0, 255, 0)  # Default green
                
                if video.waiting_for_ack:
                    status_text = "WAITING FOR ACK"
                    # Yellow color BGR(0,190,246) for waiting messages
                    color = (0, 190, 246)
                elif initial_send:
                    if len(video.movement_buffers['roi_1']) >= 30:
                        status_text = "READY FOR INITIAL SEND"
                    else:
                        status_text = f"COLLECTING DATA: {len(video.movement_buffers['roi_1'])}/30"
                else:
                    status_text = "PROCESSING DATA..."

                # Draw status message
                cv2.putText(frame_copy, status_text, (10, y_pos), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                
                video.show_frame(frame_copy, window_name)
                
                # Check for commands
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    print("\nQuitting...")
                    break
                elif key == ord('r'):
                    print("\nStarting ROI selection...")
                    video.select_single_roi(frame)
                elif key == ord('s'):
                    print("\nStarting multi-ROI selection...")
                    video.select_all_rois(frame)
                elif key == ord('t'):
                    video.show_rois = not video.show_rois
                    print(f"\nROI display: {'ON' if video.show_rois else 'OFF'}")
                elif key == ord('f'):
                    # Toggle fullscreen
                    is_fs = cv2.getWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN) != 0
                    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN,
                                        cv2.WINDOW_NORMAL if is_fs else cv2.WINDOW_FULLSCREEN)
                    print(f"\nFullscreen: {'OFF' if is_fs else 'ON'}")
    except Exception as e:
        print(f"\nError in main loop: {e}")
    finally:
        # Clean up
        video.close()
        cv2.destroyAllWindows()
        
        # Cancel server task
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            print("\nServer task cancelled")

def main():
    parser = argparse.ArgumentParser(description='Test video input with Venice live stream')
    parser.add_argument('--fullscreen', action='store_true', help='Start in fullscreen mode')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    args = parser.parse_args()
    
    asyncio.run(test_video_input(fullscreen=args.fullscreen, debug=args.debug))

if __name__ == "__main__":
    main() 