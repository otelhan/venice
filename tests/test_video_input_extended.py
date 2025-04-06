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
        
        # Thread-related attributes
        self.ack_server_thread = None
        self.message_queue = queue.Queue()
        self.server_running = False
        self.ack_received_event = threading.Event()
        
        # Print ACK info
        output_config = self.config['controllers'].get(self.ack_destination)
        if output_config:
            print(f"\nWill receive acknowledgments from: {self.ack_destination}")
            print(f"On listen port: {self.listen_port}")
        else:
            print(f"\nWarning: No configuration found for ACK source: {self.ack_destination}")
    
    def start_ack_server_thread(self):
        """Start the acknowledgment server in a separate thread"""
        if self.ack_server_thread is None or not self.ack_server_thread.is_alive():
            self.server_running = True
            self.ack_server_thread = threading.Thread(
                target=self._run_ack_server,
                daemon=True  # This ensures the thread will exit when the main program exits
            )
            self.ack_server_thread.start()
            print(f"\n[THREAD] Started acknowledgment server thread")
    
    def _run_ack_server(self):
        """Run the acknowledgment server in a thread"""
        try:
            print(f"\n[THREAD] Starting acknowledgment server on port {self.listen_port}")
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run the server
            server = websockets.serve(
                self._handle_connection_async,
                "0.0.0.0",  # Listen on all interfaces
                self.listen_port,
                ping_interval=None
            )
            
            loop.run_until_complete(server)
            loop.run_forever()
        except Exception as e:
            print(f"\n[ERROR] Error in acknowledgment server thread: {e}")
            traceback.print_exc()
            self.server_running = False
    
    async def _handle_connection_async(self, websocket):
        """Handle incoming WebSocket connections (runs in the server thread)"""
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get('type') == 'ack':
                        print("\n[ACK RECEIVED] Acknowledgment from output controller:")
                        print(json.dumps(data, indent=2))
                        
                        # Update state variables
                        self.waiting_for_ack = False
                        self.message_sent = False
                        self.should_send_next = True
                        
                        # Signal to the main thread that an ack was received
                        self.ack_received_event.set()
                        
                        print(f"[STATUS] Ready to send next data packet")
                except json.JSONDecodeError:
                    print(f"\n[ERROR] Invalid JSON received: {message}")
                        
        except websockets.exceptions.ConnectionClosed:
            print("\n[ERROR] Acknowledgement connection closed")
        except Exception as e:
            print(f"\n[ERROR] Error handling acknowledgement: {e}")
            traceback.print_exc()
    
    def _enqueue_message(self, data):
        """Add a message to the queue for sending in the sender thread"""
        self.message_queue.put(data)
        
    def start_sender_thread(self):
        """Start a thread for sending messages to the controller"""
        sender_thread = threading.Thread(
            target=self._run_sender_loop,
            daemon=True
        )
        sender_thread.start()
        print(f"\n[THREAD] Started message sender thread")
        return sender_thread
    
    def _run_sender_loop(self):
        """Run the sender loop in a thread"""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            while True:
                try:
                    # Get the next message from the queue, with a timeout
                    try:
                        data = self.message_queue.get(timeout=0.5)
                    except queue.Empty:
                        # No message to send, just continue the loop
                        continue
                    
                    # Send the message
                    success = loop.run_until_complete(self._send_to_controller_async(data))
                    
                    if success:
                        # Mark the task as done
                        self.message_queue.task_done()
                    else:
                        # Put the message back in the queue to retry later
                        self.message_queue.put(data)
                        time.sleep(2)  # Wait before retrying
                        
                except Exception as e:
                    print(f"\n[ERROR] Error in sender thread: {e}")
                    traceback.print_exc()
                    time.sleep(1)  # Avoid tight loop in case of error
                    
        except Exception as e:
            print(f"\n[ERROR] Sender thread crashed: {e}")
            traceback.print_exc()
    
    async def _send_to_controller_async(self, data):
        """Send data to controller (runs in the sender thread)"""
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
                
                # Update state after successful send
                self.waiting_for_ack = True
                self.message_sent = True
                self.last_message = data
                self.should_send_next = False  # Reset flag after sending
                
                # Reset the acknowledgment event
                self.ack_received_event.clear()
                
                print(f"[STATUS] Now waiting for acknowledgment from {self.ack_destination}")
                return True

        except Exception as e:
            print(f"\n[ERROR] Failed to send to controller: {e}")
            return False
    
    async def send_to_controller(self, data):
        """Override send_to_controller to use the thread-based approach"""
        if self.waiting_for_ack:
            print("\n[STATUS] Already waiting for acknowledgment, cannot send new data")
            return False

        # Start the ack server thread if it's not already running
        if not self.server_running:
            self.start_ack_server_thread()
            # Give it a moment to start
            await asyncio.sleep(1)
            
        # Enqueue the message for sending
        self._enqueue_message(data)
        
        # The actual sending will be handled by the sender thread
        return True
    
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
            # Print status message every 30 calls (to avoid flooding terminal)
            if hasattr(self, 'ack_wait_count'):
                self.ack_wait_count += 1
                if self.ack_wait_count % 30 == 0:
                    print(f"\n[STATUS] Still waiting for acknowledgment from {self.ack_destination}...")
                    # Check if it's been too long since we sent the message
                    if hasattr(self, 'last_ack_request_time'):
                        elapsed = time.time() - self.last_ack_request_time
                        if elapsed > 60:  # More than 60 seconds
                            print(f"\n[WARNING] Acknowledgment timeout (waited {elapsed:.1f}s). Resetting state...")
                            self.waiting_for_ack = False
                            self.should_send_next = True
            else:
                self.ack_wait_count = 1
                self.last_ack_request_time = time.time()
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
    
    # Start the acknowledgment server and sender threads
    video.start_ack_server_thread()
    sender_thread = video.start_sender_thread()
    
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
                            # Check if we need to send data based on ack status
                            await video.check_and_try_send()
                            
                except Exception as e:
                    print(f"\nError processing frame: {e}")
                    import traceback
                    traceback.print_exc()
                
                # Create a copy of the frame for visualization
                display_frame = frame.copy()
                
                # Add status overlay
                # Current time in Venice timezone
                venice_time = video.get_venice_time()
                time_str = venice_time.strftime("%H:%M:%S")
                cv2.putText(
                    display_frame, 
                    f"Frame: {frame_count} | Venice Time: {time_str}",
                    (10, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 
                    0.7, 
                    (0, 255, 0), 
                    2
                )
                
                # Status message at the bottom
                if video.waiting_for_ack:
                    status_text = "WAITING FOR ACK"
                    color = (0, 190, 246)  # Yellow in BGR
                else:
                    status_text = "READY"
                    color = (0, 255, 0)  # Green
                
                # Draw the status text
                cv2.putText(
                    display_frame,
                    status_text,
                    (10, 80),  # Position (80 pixels from top)
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,  # Larger text
                    color,
                    2  # Thicker
                )
                
                # Show frame with overlays
                video.show_frame(display_frame, window_name)
                
                # Handle keypresses
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    print("\nQuitting...")
                    break
                elif key == ord('s'):
                    # Run ROI selection with full grid
                    print("\nSelect all ROIs:")
                    video.select_all_rois(frame)
                elif key == ord('r'):
                    # Run ROI selection for a single ROI
                    print("\nSelect single ROI:")
                    video.select_single_roi(frame)
                elif key == ord('t'):
                    # Toggle ROI display
                    video.show_rois = not video.show_rois
                    print(f"\nROI display: {'On' if video.show_rois else 'Off'}")
                elif key == ord('f'):
                    # Toggle fullscreen
                    if cv2.getWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN) == cv2.WINDOW_FULLSCREEN:
                        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
                        print("\nExited fullscreen mode")
                    else:
                        cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                        print("\nEntered fullscreen mode")
            else:
                # If no frame, short sleep to prevent CPU spinning
                await asyncio.sleep(0.1)
                
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    finally:
        video.close()
        sender_thread.join()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test video input module')
    parser.add_argument('--fullscreen', action='store_true', help='Start in fullscreen mode')
    parser.add_argument('--debug', action='store_true', help='Show debug information')
    args = parser.parse_args()
    
    # Run the test function
    asyncio.run(test_video_input(fullscreen=args.fullscreen, debug=args.debug)) 