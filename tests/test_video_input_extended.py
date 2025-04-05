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

from src.networking.video_input import VideoInput

class VideoInputWithAck(VideoInput):
    def __init__(self):
        super().__init__()
        self.waiting_for_ack = False
        self.server = None
        self.listen_port = 8777  # Port to listen for acknowledgments from output controller
        self.last_message = None
        self.message_sent = False
        self.ack_destination = 'output'  # The controller that will send ACKs
        self.should_send_next = True  # Flag to send data after receiving ACK
        
        # Print ACK info
        output_config = self.config['controllers'].get(self.ack_destination)
        if output_config:
            print(f"\nWill receive acknowledgments from: {self.ack_destination}")
            print(f"On listen port: {self.listen_port}")
        else:
            print(f"\nWarning: No configuration found for ACK source: {self.ack_destination}")

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
                    print("\n[ACK RECEIVED] Acknowledgment from output controller:")
                    print(json.dumps(data, indent=2))
                    self.waiting_for_ack = False
                    self.message_sent = False
                    self.should_send_next = True  # Flag to send next data
                    print(f"[STATUS] Ready to send next data packet")
                    
        except websockets.exceptions.ConnectionClosed:
            print("\n[ERROR] Acknowledgement connection closed")
        except Exception as e:
            print(f"\n[ERROR] Error handling acknowledgement: {e}")

    async def send_to_controller(self, data):
        """Override send_to_controller to wait for acknowledgment"""
        if self.waiting_for_ack:
            print("\n[STATUS] Already waiting for acknowledgment, cannot send new data")
            return False

        try:
            # Get controller config
            dest_config = self.config['controllers'].get(self.destination)
            if not dest_config:
                print(f"\n[ERROR] No configuration found for destination: {self.destination}")
                return False

            # Connect to controller
            uri = f"ws://{dest_config['ip']}:{dest_config.get('listen_port', 8765)}"
            print(f"\n[STATUS] Connecting to {self.destination}:")
            print(f"URI: {uri}")
            
            async with websockets.connect(uri) as websocket:
                print(f"[SUCCESS] Connected to {self.destination}")
                await websocket.send(json.dumps(data))
                print(f"[SUCCESS] Data sent to {self.destination}")
                if len(data.get('data', {}).get('pot_values', [])) > 0:
                    timestamp = data.get('timestamp', 'unknown')
                    pot_count = len(data.get('data', {}).get('pot_values', []))
                    print(f"[DATA] Timestamp: {timestamp}")
                    print(f"[DATA] Sent {pot_count} movement values")
                
                self.waiting_for_ack = True
                self.message_sent = True
                self.last_message = data
                self.should_send_next = False  # Reset flag after sending
                print(f"[STATUS] Now waiting for acknowledgment from {self.ack_destination}")
                return True

        except Exception as e:
            print(f"\n[ERROR] Failed to send to controller: {e}")
            return False
    
    async def check_and_try_send(self):
        """Check if we should send data to controller"""
        if self.should_send_next and not self.waiting_for_ack:
            if len(self.movement_buffers['roi_1']) >= 30:
                print("\n[STATUS] Sending latest movement data to controller...")
                await self.send_movement_vector()
                return True
            else:
                print(f"\n[STATUS] Not enough data to send: {len(self.movement_buffers['roi_1'])}/30 values")
                return False
        elif self.waiting_for_ack:
            # Print status message every 10 calls (to avoid flooding terminal)
            if hasattr(self, 'ack_wait_count'):
                self.ack_wait_count += 1
                if self.ack_wait_count % 10 == 0:
                    print(f"\n[STATUS] Still waiting for acknowledgment from {self.ack_destination}...")
            else:
                self.ack_wait_count = 1
                print(f"\n[STATUS] Waiting for acknowledgment from {self.ack_destination}...")
        return False

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
        video.last_vector_time = 0  # Reset the last vector time to ensure immediate vector calculation
        video.last_save_time = 0    # Reset the last save time to ensure immediate saving
        
        frame_count = 0
        initial_send = True  # Flag to send first data
        
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
                        
                        # Initial data send or after receiving ACK
                        if initial_send and len(video.movement_buffers['roi_1']) >= 30:
                            print("\n[INIT] Sending initial data packet...")
                            await video.send_movement_vector()
                            initial_send = False
                        else:
                            # Try to send if acknowledgment received
                            send_attempted = await video.check_and_try_send()
                            if send_attempted:
                                print(f"[STATUS] Successfully attempted to send new data after ACK")
                        
                except Exception as e:
                    print(f"\nError in processing: {e}")
                
                # Show frame with status message
                frame_copy = frame.copy()
                
                # Add status messages
                status_messages = []
                
                # Connection status
                if video.message_sent:
                    if video.waiting_for_ack:
                        status_messages.append("WAITING FOR ACK FROM OUTPUT")
                    else:
                        status_messages.append("READY TO SEND NEXT DATA")
                else:
                    if initial_send:
                        if len(video.movement_buffers['roi_1']) >= 30:
                            status_messages.append("READY FOR INITIAL SEND")
                        else:
                            status_messages.append(f"COLLECTING DATA: {len(video.movement_buffers['roi_1'])}/30")
                    else:
                        status_messages.append("PROCESSING DATA...")
                
                # Add buffer status
                buffer_status = f"BUFFER: {len(video.movement_buffers['roi_1'])} values"
                status_messages.append(buffer_status)
                
                # Display all status messages
                for i, msg in enumerate(status_messages):
                    cv2.putText(frame_copy, msg, (10, 60 + i*30), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                
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
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Test Video Input with Acknowledgment')
    parser.add_argument('--fullscreen', '-f', action='store_true', 
                        help='Start in fullscreen mode')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug output with frame-by-frame data')
    args = parser.parse_args()
    
    # Run test with fullscreen option from command line
    asyncio.run(test_video_input(fullscreen=args.fullscreen, debug=args.debug)) 