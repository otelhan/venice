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

# Add project root to path
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from src.networking.video_input import VideoInput

class VideoInputWithAck(VideoInput):
    def __init__(self):
        super().__init__()
        self.waiting_for_ack = False
        self.server = None
        self.listen_port = 8777  # Same as builder's listen port
        self.last_message = None
        self.message_sent = False

    async def start_ack_server(self):
        """Start WebSocket server to receive acknowledgments"""
        print(f"\nStarting acknowledgment server on port {self.listen_port}")
        async with websockets.serve(
            self.handle_connection,
            "0.0.0.0",  # Listen on all interfaces
            self.listen_port,
            ping_interval=None
        ) as server:
            self.server = server
            await asyncio.Future()  # run forever

    async def handle_connection(self, websocket):
        """Handle incoming WebSocket connections"""
        try:
            async for message in websocket:
                data = json.loads(message)
                if data.get('type') == 'ack':
                    print("\nReceived acknowledgement")
                    print(json.dumps(data, indent=2))
                    self.waiting_for_ack = False
                    self.message_sent = False
                    
        except websockets.exceptions.ConnectionClosed:
            print("\nAcknowledgement connection closed")
        except Exception as e:
            print(f"Error handling acknowledgement: {e}")

    async def send_to_controller(self, data):
        """Override send_to_controller to wait for acknowledgment"""
        if self.waiting_for_ack:
            print("\nWaiting for acknowledgment before sending next data...")
            return False

        try:
            # Get controller config
            dest_config = self.config['controllers'].get(self.destination)
            if not dest_config:
                print(f"No configuration found for destination: {self.destination}")
                return False

            # Connect to controller
            uri = f"ws://{dest_config['ip']}:{dest_config.get('listen_port', 8765)}"
            print(f"\nConnecting to {self.destination}:")
            print(f"URI: {uri}")
            
            async with websockets.connect(uri) as websocket:
                print(f"Connected to {self.destination}")
                await websocket.send(json.dumps(data))
                print(f"Data sent to {self.destination}:")
                print(json.dumps(data, indent=2))
                self.waiting_for_ack = True
                self.message_sent = True
                self.last_message = data
                return True

        except Exception as e:
            print(f"Error sending to controller: {e}")
            return False

async def test_video_input(fullscreen=False):
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
    
    # Start acknowledgment server
    server_task = asyncio.create_task(video.start_ack_server())
    
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
                        
                        # Check and perform save if needed
                        save_performed = await video.check_and_save()
                        if save_performed:
                            print(f"\nSaved movement vector at {video.get_venice_time()}")
                        
                        # Force a save check every 30 seconds
                        current_time = time.time()
                        if current_time - last_save_time >= 30.0:
                            # Force creation of CSV file even with empty buffer
                            print(f"\nForcing CSV file creation at {video.get_venice_time()}")
                            
                            # Fill buffer with dummy data if needed
                            if len(video.movement_buffers['roi_1']) < 30:
                                missing_values = 30 - len(video.movement_buffers['roi_1'])
                                print(f"Adding {missing_values} dummy values to buffer")
                                for i in range(missing_values):
                                    video.movement_buffers['roi_1'].append(50.0)  # Add medium movement value
                            
                            # Now try to save
                            await video.save_movement_vector()
                            last_save_time = current_time
                            
                except Exception as e:
                    print(f"\nError in processing: {e}")
                
                # Show frame with status message
                frame_copy = frame.copy()
                if video.message_sent:
                    status = "Data sent to reservoir, waiting..." if video.waiting_for_ack else "Processing data..."
                    cv2.putText(frame_copy, status, (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
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
                    print("\nStarting all ROIs selection...")
                    video.select_all_rois(frame)
                elif key == ord('t'):
                    video.show_rois = not video.show_rois
                    print(f"\nROI display: {'On' if video.show_rois else 'Off'}")
                elif key == ord('f'):
                    fullscreen = not fullscreen
                    if fullscreen:
                        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                    else:
                        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
                    print(f"\nFullscreen: {'On' if fullscreen else 'Off'}")
                
                # Give control back to event loop occasionally
                await asyncio.sleep(0)
                
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    finally:
        video.close()
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    asyncio.run(test_video_input()) 