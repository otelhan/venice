from src.core.camera_handler import CameraHandler
import time

def test_camera():
    """Test camera functionality with energy plotting"""
    print("=== Starting Camera Test with Energy Plot ===")
    print("You will see:")
    print("1. Grayscale camera feed")
    print("2. Real-time energy plot in a separate window")
    print("Move something in front of the camera to see energy changes")
    print("Press 'q' to exit")
    
    camera = CameraHandler()
    
    try:
        if camera.start_camera():
            print("Press 'q' to stop camera feed")
            while True:
                if not camera.show_frame():
                    break
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        camera.stop_camera()
    
    print("\n=== Camera Test Complete ===")

if __name__ == "__main__":
    test_camera() 