from src.core.video_processor import VideoProcessor
import numpy as np

def test_video_processor():
    processor = VideoProcessor()
    processor.load_video("input_videos/Ponte delle Guglie_night.mp4")
    processor.select_roi()
    movements = processor.calculate_movement()
    print(f"Detected {len(movements)} movement measurements")
    print(f"Average movement: {np.mean(movements):.2f}")
    print(f"Max movement: {np.max(movements):.2f}")

if __name__ == "__main__":
    test_video_processor() 