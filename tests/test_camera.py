import cv2
import time
import numpy as np
import matplotlib.pyplot as plt

def test_raspi_camera():
    """Test camera capture and display on Raspberry Pi"""
    print("\nStarting Raspberry Pi camera test...")
    
    # Initialize camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open camera")
        return False
        
    # Create windows
    cv2.namedWindow('Camera Test', cv2.WINDOW_NORMAL)
    plt.ion()  # Interactive mode for matplotlib
    fig, ax = plt.subplots()
    line, = ax.plot([], [])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 255)
    plt.show()
    
    # Test variables
    frame_count = 0
    start_time = time.time()
    values = []
    
    print("\nPress 'q' to quit test")
    
    try:
        while True:
            # Capture frame
            ret, frame = cap.read()
            if not ret:
                print("ERROR: Failed to grab frame")
                break
                
            # Calculate average brightness
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            avg_brightness = np.mean(gray)
            values.append(avg_brightness)
            
            # Update plot
            if len(values) > 100:
                values.pop(0)
            line.set_data(range(len(values)), values)
            fig.canvas.draw()
            fig.canvas.flush_events()
            
            # Show frame
            cv2.imshow('Camera Test', frame)
            frame_count += 1
            
            # Check for quit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
                
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        # Cleanup
        cap.release()
        cv2.destroyAllWindows()
        plt.close()
        
        # Print results
        duration = time.time() - start_time
        fps = frame_count / duration
        print(f"\nTest Results:")
        print(f"Frames captured: {frame_count}")
        print(f"Duration: {duration:.1f} seconds")
        print(f"Average FPS: {fps:.1f}")
        
if __name__ == "__main__":
    test_raspi_camera() 