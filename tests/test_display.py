import cv2
import time
import numpy as np
import matplotlib.pyplot as plt
from threading import Lock

def test_display():
    """Test camera and display functionality"""
    print("\nTesting camera and display...")
    
    # Initialize camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open camera")
        return
    
    # Create windows
    cv2.namedWindow('Camera Test', cv2.WINDOW_NORMAL)
    
    # Setup plotting
    plt.ion()  # Interactive mode
    fig, ax = plt.subplots(figsize=(10, 6))
    line, = ax.plot([], [], 'b-', linewidth=2)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 8)
    ax.set_title('Energy Values')
    ax.grid(True)
    plt.show()
    
    # Test variables
    values = []
    plot_lock = Lock()
    
    print("\nPress 'q' to quit test")
    
    try:
        while True:
            # Read camera
            ret, frame = cap.read()
            if not ret:
                print("ERROR: Could not read frame")
                break
            
            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Calculate energy (entropy)
            histogram = cv2.calcHist([gray], [0], None, [256], [0, 256])
            histogram = histogram.ravel() / histogram.sum()
            non_zero = histogram > 0
            energy = -np.sum(histogram[non_zero] * np.log2(histogram[non_zero]))
            
            # Update plot
            with plot_lock:
                values.append(energy)
                if len(values) > 100:
                    values.pop(0)
                line.set_data(range(len(values)), values)
                fig.canvas.draw()
                fig.canvas.flush_events()
            
            # Show camera feed
            cv2.imshow('Camera Test', frame)
            
            # Check for quit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            
            # Small delay
            time.sleep(0.01)
            
    except Exception as e:
        print(f"Error during test: {e}")
        
    finally:
        cap.release()
        cv2.destroyAllWindows()
        plt.close()

if __name__ == "__main__":
    test_display() 