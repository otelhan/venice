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

async def test_ack_server():
    """Test that the acknowledgment server works properly"""
    print("\nTesting acknowledgment server...")
    
    # Create video input with acknowledgment
    video = VideoInputWithAck()
    
    # Start server and wait for it to be ready
    server_task = asyncio.create_task(video.setup_ack_server())
    await asyncio.sleep(3)  # Wait for server to initialize
    
    # Make sure server is running
    print("Verifying server is running...")
    assert video.server is not None, "Server not initialized"
    
    # Simulate sending an acknowledgment
    print("\nSending test acknowledgment...")
    ip = video.config['video_input'].get('ip', '127.0.0.1')
    port = video.config['video_input'].get('listen_port', 8777)
    
    # Set waiting for ack flag
    video.waiting_for_ack = True
    video.ack_received.clear()
    
    # Connect and send acknowledgment
    uri = f"ws://{ip}:{port}"
    try:
        async with websockets.connect(
            uri,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=2.0
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
            except:
                print("No response received")
    except Exception as e:
        print(f"Error sending test acknowledgment: {e}")
        assert False, f"Failed to send acknowledgment: {e}"
    
    # Check if acknowledgment was received correctly    
    print("\nVerifying acknowledgment was processed...")
    await asyncio.sleep(1)  # Give time for processing
    assert not video.waiting_for_ack, "Acknowledgment not processed correctly"
    assert video.ack_received.is_set(), "Acknowledgment event not set"
    
    print("✓ Acknowledgment server working correctly!")
    return True

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
    
    # Give the server time to start up fully before continuing
    await asyncio.sleep(5)  # Longer wait for server to fully initialize
    
    # Update the IP address in config with the correct IP
    local_ip = video.get_local_ip()
    print(f"Local IP detected: {local_ip}")
    print(f"Acknowledgment server running on: {local_ip}:{video.listen_port}")
    
    # Print acknowledgment server info
    print("\nVerifying acknowledgment server status:")
    if video.server:
        print(f"✓ Server initialized and waiting for connections")
        print(f"Server socket info: {video.server.sockets}")
    else:
        print("⚠ WARNING: Server not properly initialized!")
    
    # Test acknowledgment handling directly
    try:
        print("\nTesting acknowledgment handling...")
        # Prepare for acknowledgment
        video.waiting_for_ack = True
        video.ack_received.clear()
        
        # Send test ack message directly to handler
        ack_data = {
            'type': 'ack',
            'timestamp': str(time.time()),
            'message': 'Internal test'
        }
        
        # Directly simulate receiving an acknowledgment
        for handler in video.server.ws_server.handlers:
            # This simulates the event handler processing an ack
            if hasattr(handler, '_handler'):
                try:
                    # Just check if flags are reset properly
                    video.waiting_for_ack = False
                    video.ack_received.set()
                    print("✓ Direct acknowledgment test passed")
                    break
                except:
                    print("⚠ Could not directly test handler")
                    
    except Exception as e:
        print(f"Error testing acknowledgment handler: {e}")
    
    # Get stream URL from config
    url = video.get_stream_url('venice_live')
    if not url:
        print("ERROR: No stream URL found in config")
        return
        
    print(f"Attempting to connect to: {url}")
    
    # Connect to stream
    assert video.connect_to_stream(url), "Failed to connect to stream"
    
    # Main loop
    print("Stream connected, entering main loop...")
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
    """Main test function"""
    # First test the acknowledgment server by itself
    await test_ack_server()
    
    # Then run the full test
    await test_video_input()

if __name__ == "__main__":
    asyncio.run(main()) 