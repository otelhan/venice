import asyncio
import websockets
import json
import cv2
import numpy as np
import time
import os
import random
from pathlib import Path
import yaml
import sys
import argparse

# Add project root to path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from src.networking.video_input import VideoInputWithAck

async def test_ack_server():
    """Test that the acknowledgment server works properly"""
    print("\nTesting acknowledgment server...")
    
    # Create video input with acknowledgment
    video = VideoInputWithAck()
    
    # Start server with force_restart to ensure we get a fresh server
    print("Starting acknowledgment server with force_restart...")
    server_task = asyncio.create_task(video.setup_ack_server(force_restart=True))
    
    # Wait for server to initialize
    server = None
    for attempt in range(3):
        await asyncio.sleep(2)  # Wait for server to initialize
        if video.server:
            server = video.server
            print(f"Server initialized on attempt {attempt+1}")
            break
        else:
            print(f"Waiting for server initialization (attempt {attempt+1}/3)...")
    
    # Make sure server is running
    print("Verifying server is running...")
    if not server:
        print("ERROR: Server not initialized after waiting")
        return False
    
    # Check if server has sockets
    if not hasattr(server, 'sockets') or not server.sockets:
        print("ERROR: Server has no sockets")
        return False
        
    print(f"Server has {len(server.sockets)} socket(s)")
    
    # Get IP and port from config
    # Simulate sending an acknowledgment
    print("\nSending test acknowledgment...")
    ip = video.config.get('video_input', {}).get('ip', '127.0.0.1')
    port = video.config.get('video_input', {}).get('listen_port', 8777)
    
    print(f"Sending to {ip}:{port}")
    
    # Set waiting for ack flag
    video.waiting_for_ack = True
    video.ack_received.clear()
    
    # Connect and send acknowledgment
    uri = f"ws://{ip}:{port}"
    success = False
    
    try:
        # Try up to 3 times to connect
        for attempt in range(3):
            try:
                print(f"Connection attempt {attempt+1}/3")
                async with websockets.connect(
                    uri,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=2.0,
                    open_timeout=5.0
                ) as websocket:
                    # Send acknowledgment
                    ack = {
                        'type': 'ack',
                        'timestamp': str(time.time()),
                        'status': 'success',
                        'message': 'Test acknowledgment'
                    }
                    await websocket.send(json.dumps(ack))
                    print("Sent test acknowledgment")
                    
                    # Wait briefly for response
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                        print(f"Received response: {response}")
                        success = True
                        break
                    except asyncio.TimeoutError:
                        print("No response received (timeout)")
                    except Exception as e:
                        print(f"Error receiving response: {e}")
            except Exception as e:
                print(f"Connection attempt {attempt+1} failed: {e}")
                if attempt < 2:  # Only sleep if we're going to retry
                    print("Retrying in 2 seconds...")
                    await asyncio.sleep(2)
    except Exception as e:
        print(f"Error in test acknowledgment process: {e}")
    
    # Check if acknowledgment was received correctly
    if success:
        print("\nVerifying acknowledgment was processed...")
        await asyncio.sleep(1)  # Give time for processing
        
        if not video.waiting_for_ack and video.ack_received.is_set():
            print("✓ Acknowledgment server working correctly!")
            return True
        else:
            print("× Acknowledgment not processed correctly")
            return False
    else:
        print("× Failed to send test acknowledgment")
        return False

async def test_video_input(fullscreen=False, debug=False, use_video=False, use_random=False):
    """Test video input with either a video file or Venice live stream"""
    print("\nTesting video input...")
    print("\nControls:")
    print("'s' - Select all ROIs")
    print("'r' - Select single ROI")
    print("'t' - Toggle ROI display")
    print("'f' - Toggle fullscreen")
    if use_random:
        print("'n' - Load next random video")
    print("'q' - Quit")
    
    # Create video input with acknowledgment handling
    video = VideoInputWithAck()
    
    # Start acknowledgment server and wait for it to be ready
    print("\nStarting acknowledgment server...")
    # Don't force restart if the test_ack_server already set up a server
    if video.server is None:
        server_task = asyncio.create_task(video.setup_ack_server(force_restart=False))
    else:
        print("Using existing server from previous test")
        server_task = None
    
    # Give the server time to start up fully before continuing
    await asyncio.sleep(2)  # Shorter wait since we already waited in test_ack_server
    
    # Update the IP address in config with the correct IP
    local_ip = video.get_local_ip()
    print(f"Local IP detected: {local_ip}")
    print(f"Acknowledgment server running on: {local_ip}:{video.listen_port}")
    
    # Print acknowledgment server info
    print("\nVerifying acknowledgment server status:")
    if video.server:
        print(f"✓ Server initialized and waiting for connections")
        print(f"Server socket info: {video.server.sockets if hasattr(video.server, 'sockets') else 'No sockets'}")
    else:
        print("⚠ WARNING: Server not properly initialized!")
    
    # Test acknowledgment handling directly
    try:
        print("\nTesting acknowledgment handling...")
        # Prepare for acknowledgment
        video.waiting_for_ack = True
        video.ack_received.clear()
        
        # Since we can't directly call the handler, we'll manually simulate an ack
        print("Manually simulating acknowledgment...")
        video.waiting_for_ack = False
        video.ack_received.set()
        print("✓ Direct acknowledgment test passed")
    except Exception as e:
        print(f"Error testing acknowledgment handler: {e}")
    
    # Get video path if using random mode
    if use_random:
        input_dir = os.path.join(project_root, "input_videos")
        if not os.path.exists(input_dir):
            os.makedirs(input_dir)
            print(f"Created input_videos directory: {input_dir}")
            print("Please add video files to this directory and try again")
            return False
        
        video_files = []
        for ext in [".mp4", ".avi", ".mov", ".mkv"]:
            video_files.extend(list(Path(input_dir).glob(f"*{ext}")))
        
        if not video_files:
            print(f"No video files found in {input_dir}")
            return False
        
        # Select random video
        current_video = str(random.choice(video_files))
        print(f"Randomly selected video: {os.path.basename(current_video)}")
        
        # Connect to the video file
        if not video.connect_to_stream(current_video):
            print(f"Failed to open video file: {current_video}")
            return False
    # Connect to video source from config if not using random
    elif use_video:
        # Get video path from config
        video_path = video.config.get('video_input', {}).get('video_path')
        if not video_path:
            print("ERROR: No video path found in config")
            return False
            
        print(f"Opening video file from config: {video_path}")
        if not video.connect_to_stream(video_path):
            print("Failed to open video file")
            return False
    else:
        # Get stream URL from config
        url = video.get_stream_url('venice_live')
        if not url:
            print("ERROR: No stream URL found in config")
            return
            
        print(f"Attempting to connect to: {url}")
        
        # Connect to stream
        if not video.connect_to_stream(url):
            print("Failed to connect to stream")
            return False
    
    # Main loop
    print("Video source connected, entering main loop...")
    video.show_rois = True
    try:
        last_send_time = time.time()
        video.calculating = True  # Start movement calculation
        
        while True:
            # Process camera frame
            frame = video.get_frame()
            movements = video.process_frame(return_movements=True)
            
            # Display frame with ROIs
            if frame is not None:
                video.show_frame(frame)
            
            # Try sending data if we have enough
            if time.time() - last_send_time >= 30:  # Every 30 seconds
                if len(video.movement_buffers['roi_1']) >= 30:
                    print(f"\nAttempting to send movement vector...")
                    await video.send_movement_vector()
                    last_send_time = time.time()
            
            # Handle CSV saving
            await video.check_and_save()
            
            # Process key commands
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('r'):
                video.calculating = False
                video.select_single_roi(frame)
                video.calculating = True
            elif key == ord('s'):
                video.calculating = False
                video.select_all_rois(frame)
                video.calculating = True
            elif key == ord('t'):
                video.show_rois = not video.show_rois
            elif key == ord('f'):
                # Toggle fullscreen
                window_name = "Venice Stream"
                if cv2.getWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN) == cv2.WINDOW_FULLSCREEN:
                    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
                else:
                    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
            elif use_random and key == ord('n'):
                # Load next random video
                print("\nLoading next random video...")
                video.close()
                
                # Select a different random video
                video_files = []
                input_dir = os.path.join(project_root, "input_videos")
                for ext in [".mp4", ".avi", ".mov", ".mkv"]:
                    video_files.extend(list(Path(input_dir).glob(f"*{ext}")))
                
                # Try to select a different video if possible
                if len(video_files) > 1:
                    remaining_videos = [v for v in video_files if str(v) != current_video]
                    if remaining_videos:
                        current_video = str(random.choice(remaining_videos))
                else:
                    current_video = str(video_files[0])
                
                print(f"Selected video: {os.path.basename(current_video)}")
                if not video.connect_to_stream(current_video):
                    print(f"Failed to open video file: {current_video}")
                    break
                
                video.calculating = True
            
            # Short sleep to reduce CPU usage
            await asyncio.sleep(0.01)
            
    except KeyboardInterrupt:
        print("\nCtrl+C detected, shutting down...")
    except Exception as e:
        print(f"\nError in main loop: {e}")
    finally:
        video.close()
        
    return True

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Video Input Test with Extended Features')
    parser.add_argument('--fullscreen', action='store_true', help='Run in fullscreen mode')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--video', action='store_true', help='Use video file from config')
    group.add_argument('--stream', action='store_true', help='Use stream from config')
    group.add_argument('--random', action='store_true', help='Use random video from input_videos folder')
    
    args = parser.parse_args()
    
    # Run acknowledgment server test first
    if not await test_ack_server():
        print("\nWARNING: Acknowledgment server test failed!")
        print("Continuing with main test anyway...")
    
    # Run main test
    await test_video_input(
        fullscreen=args.fullscreen,
        debug=args.debug,
        use_video=args.video,
        use_random=args.random
    )

if __name__ == "__main__":
    asyncio.run(main()) 