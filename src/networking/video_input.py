import cv2
import numpy as np
from typing import Optional
import time
import yt_dlp

class VideoInput:
    def __init__(self):
        self.stream = None
        self.cap = None
        self.frame_count = 0
        self.last_frame = None
        self.is_running = False
        
    def connect_to_stream(self, url: str) -> bool:
        """Connect to YouTube stream"""
        try:
            print(f"Connecting to: {url}")
            
            # Configure yt-dlp
            ydl_opts = {
                'format': 'best',  # Get best quality
                'quiet': True,     # Reduce output
            }
            
            # Get stream URL using yt-dlp
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info['url']
                
            # Open video stream
            self.cap = cv2.VideoCapture(stream_url)
            if not self.cap.isOpened():
                print("ERROR: Could not open stream")
                return False
                
            self.is_running = True
            print(f"Connected to stream: {info.get('title', 'Unknown')}")
            return True
            
        except Exception as e:
            print(f"Error connecting to stream: {e}")
            return False
            
    def get_frame(self) -> Optional[np.ndarray]:
        """Get current frame from stream"""
        if not self.is_running:
            return None
            
        try:
            ret, frame = self.cap.read()
            if ret:
                self.last_frame = frame
                self.frame_count += 1
                return frame
            return None
            
        except Exception as e:
            print(f"Error reading frame: {e}")
            return None
            
    def show_frame(self, frame: np.ndarray, window_name: str = 'Stream') -> bool:
        """Display frame in window"""
        try:
            # Resize if frame is too large
            height, width = frame.shape[:2]
            if width > 1280:  # Max width
                scale = 1280 / width
                new_width = int(width * scale)
                new_height = int(height * scale)
                frame = cv2.resize(frame, (new_width, new_height))
                
            cv2.imshow(window_name, frame)
            return cv2.waitKey(1) & 0xFF != ord('q')
            
        except Exception as e:
            print(f"Error showing frame: {e}")
            return False
            
    def close(self):
        """Clean up resources"""
        self.is_running = False
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows() 