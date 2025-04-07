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
        self.ack_wait_count = 0
        self.ack_timeout = 30  # seconds to wait before resending data
        self.last_ack_time = time.time()
        self.status_message = "INITIALIZING..."
        self.current_connection_task = None  # Track current connection attempt
        
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
                    self.last_ack_time = time.time()
                    self.status_message = "READY TO SEND NEXT DATA"
                    print(f"[STATUS] Ready to send next data packet")
                    
        except websockets.exceptions.ConnectionClosed:
            print("\n[ERROR] Acknowledgement connection closed")
        except Exception as e:
            print(f"\n[ERROR] Error handling acknowledgement: {e}")

    async def send_to_controller(self, data):
        """Non-blocking version that starts the send operation and returns immediately"""
        if self.waiting_for_ack:
            print("\n[STATUS] Already waiting for acknowledgment, cannot send new data")
            return False

        # Mark as waiting for acknowledgment before starting connection
        self.waiting_for_ack = True
        self.message_sent = True
        self.last_message = data
        self.should_send_next = False
        self.last_ack_time = time.time()
        self.status_message = "WAITING FOR ACK FROM OUTPUT"
        
        # Start the connection task in the background
        if self.current_connection_task is not None:
            # Cancel any existing tasks
            try:
                self.current_connection_task.cancel()
            except:
                pass
                
        # Create a new connection task
        self.current_connection_task = asyncio.create_task(
            self._connect_and_send(data)
        )
        
        # Return immediately
        print(f"\n[STATUS] Started async connection to {self.destination}")
        return True
    
    async def _connect_and_send(self, data):
        """Background task to connect and send data"""
        try:
            # Get controller config
            dest_config = self.config['controllers'].get(self.destination)
            if not dest_config:
                print(f"\n[ERROR] No configuration found for destination: {self.destination}")
                self.waiting_for_ack = False
                self.status_message = "CONNECTION ERROR"
                return False

            # Connect to controller
            uri = f"ws://{dest_config['ip']}:{dest_config.get('listen_port', 8765)}"
            print(f"\n[STATUS] Connecting to {self.destination}:")
            print(f"URI: {uri}")
            
            async with websockets.connect(uri, ping_interval=None, close_timeout=5) as websocket:
                print(f"[SUCCESS] Connected to {self.destination}")
                await websocket.send(json.dumps(data))
                print(f"[SUCCESS] Data sent to {self.destination}")
                if len(data.get('data', {}).get('pot_values', [])) > 0:
                    timestamp = data.get('timestamp', 'unknown')
                    pot_count = len(data.get('data', {}).get('pot_values', []))
                    print(f"[DATA] Timestamp: {timestamp}")
                    print(f"[DATA] Sent {pot_count} movement values")
                
                print(f"[STATUS] Now waiting for acknowledgment from {self.ack_destination}")
                return True

        except Exception as e:
            print(f"\n[ERROR] Failed to send to controller: {e}")
            # Don't reset waiting_for_ack here - let the timeout mechanism handle it
            # This prevents immediate retries which could cause connection issues
            self.status_message = f"CONNECTION ERROR: {str(e)[:30]}"
            return False
        finally:
            # Clear the task reference
            self.current_connection_task = None
    
    async def background_tasks_handler(self):
        """Handle background tasks like checking for timeouts and periodic operations"""
        while True:
            try:
                # Check for reconnection needs
                if hasattr(self, 'reconnection_needed') and self.reconnection_needed:
                    print("\n[AUTO] Attempting stream reconnection in background...")
                    # Reset the flag first to prevent multiple reconnection attempts
                    self.reconnection_needed = False
                    
                    # Try to reconnect
                    try:
                        # Get stream URL from config
                        url = self.get_stream_url('venice_live')
                        if url:
                            # Close existing connection if any
                            if self.cap:
                                self.cap.release()
                                self.cap = None
                                
                            # Reconnect to stream
                            if self.connect_to_stream(url):
                                print("[AUTO] Successfully reconnected to stream")
                            else:
                                print("[AUTO] Failed to reconnect to stream, will retry later")
                        else:
                            print("[AUTO] Cannot reconnect - no stream URL found")
                    except Exception as e:
                        print(f"[AUTO] Error during reconnection: {e}")
                
                # Check for acknowledgment timeout
                if self.waiting_for_ack and time.time() - self.last_ack_time > self.ack_timeout:
                    print(f"\n[TIMEOUT] No acknowledgment received after {self.ack_timeout} seconds")
                    print("[RECOVERY] Resetting acknowledgment state")
                    self.waiting_for_ack = False
                    self.should_send_next = True
                    self.status_message = "RETRYING AFTER TIMEOUT"
                
                # Try to send data if ready and have enough data
                if self.should_send_next and not self.waiting_for_ack:
                    if len(self.movement_buffers['roi_1']) >= 30:
                        print("\n[AUTO] Sending movement data to controller...")
                        await self.send_movement_vector()
                
                # Check for saving CSV data
                save_performed = await self.check_and_save()
                if save_performed:
                    print(f"\n[AUTO] Saved to CSV at {self.get_venice_time()}")
                
                # Update status message
                if self.waiting_for_ack:
                    # Update waiting message with time spent waiting
                    wait_time = int(time.time() - self.last_ack_time)
                    if wait_time % 5 == 0:  # Only log every 5 seconds to reduce spam
                        print(f"\n[STATUS] Waiting for acknowledgment... ({wait_time}s)")
                
            except Exception as e:
                print(f"\n[ERROR] Error in background task: {e}")
            
            # Sleep to prevent CPU overuse
            await asyncio.sleep(1)
    
    async def check_and_try_send(self):
        """Manually check if we should send data to controller (for explicit calls)"""
        if self.should_send_next and not self.waiting_for_ack:
            if len(self.movement_buffers['roi_1']) >= 30:
                print("\n[MANUAL] Sending latest movement data to controller...")
                await self.send_movement_vector()
                return True
            else:
                print(f"\n[STATUS] Not enough data to send: {len(self.movement_buffers['roi_1'])}/30 values")
                self.status_message = f"COLLECTING DATA: {len(self.movement_buffers['roi_1'])}/30"
                return False
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
    
    # Start background task handler
    background_task = asyncio.create_task(video.background_tasks_handler())
    
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
        last_status_update = 0
        fps_counter = 0
        fps_timer = time.time()
        fps = 0
        last_key_check = 0
        
        # Initial send handled by background task
        video.status_message = "STARTING UP..."
        video.reconnection_needed = False  # Initialize reconnection flag
        
        # Frame rate control
        target_fps = 30
        frame_duration = 1.0 / target_fps
        
        while True:
            # Process frames at a controlled rate
            start_time = time.time()
            
            # Get frame (non-blocking)
            frame = video.get_frame()
            if frame is not None:
                frame_count += 1
                fps_counter += 1
                
                # Process frame (always calculating but don't wait for result)
                try:
                    video.process_frame(return_movements=False)
                    
                    # Calculate FPS every second
                    current_time = time.time()
                    if current_time - fps_timer >= 1.0:
                        fps = fps_counter / (current_time - fps_timer)
                        fps_counter = 0
                        fps_timer = current_time
                        
                except Exception as e:
                    if debug:
                        print(f"\nError processing frame: {e}")
                
                # Display frame efficiently - don't copy if we don't need to
                display_frame = frame.copy() if video.show_rois else frame
                
                # Add status message
                msg = video.status_message
                # Convert RGB (246,190,0) to BGR format (0,190,246)
                # Yellow color specifically requested by user
                yellow_color = (0, 190, 246)
                color = yellow_color if "WAITING" in msg else (0, 255, 0)
                
                # Position 80 pixels from top
                cv2.putText(display_frame, msg, (10, 80), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                
                # Add FPS counter if in debug mode
                if debug:
                    cv2.putText(display_frame, f"FPS: {fps:.1f}", (10, 120),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                # Show the frame (this may use frame as is if no ROIs to show)
                video.show_frame(display_frame, window_name)
                
                # Check for key presses (don't check every frame to reduce CPU)
                current_time = time.time()
                if current_time - last_key_check >= 0.05:  # 50ms throttle for key checks
                    key = cv2.waitKey(1) & 0xFF
                    last_key_check = current_time
                    
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
            else:
                # No frame available, yield to background tasks
                await asyncio.sleep(0.01)
                continue
            
            # Adaptive frame rate control
            elapsed = time.time() - start_time
            sleep_time = max(0, min(0.033, frame_duration - elapsed))
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            else:
                # Just yield control briefly if we're behind
                await asyncio.sleep(0)
                
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    finally:
        video.close()
        server_task.cancel()
        background_task.cancel()
        try:
            await server_task
            await background_task
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