import time
from src.networking.output_node import OutputNode, ServoController

def test_servo_control():
    """Test basic servo control"""
    print("\nServo Control Test")
    print("-----------------")
    
    node = OutputNode()
    
    if not node.start():
        print("Failed to start output node")
        return
        
    try:
        # Test sequence
        commands = [
            # Test servo 1
            {
                'type': 'servo',
                'servo_id': 1,  # Change this to test different servos (1-8)
                'position': 1500,  # Center position (500-2500)
                'time_ms': 1000   # Time to reach position
            },
            # Move to min position
            {
                'type': 'servo',
                'servo_id': 1,
                'position': 500,  # Minimum position
                'time_ms': 1000
            },
            # Move to max position
            {
                'type': 'servo',
                'servo_id': 1,
                'position': 2500,  # Maximum position
                'time_ms': 1000
            }
        ]
        
        for cmd in commands:
            print(f"\nSending command: {cmd}")
            response = node.handle_command(cmd)
            print(f"Response: {response}")
            time.sleep(2)  # Wait between commands
            
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    finally:
        node.stop()

if __name__ == "__main__":
    test_servo_control() 