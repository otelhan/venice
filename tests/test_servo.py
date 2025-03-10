import time
from src.networking.output_node import OutputNode, ServoController

def test_servo_interactive():
    """Interactive servo testing"""
    print("\nServo Control Test")
    print("-----------------")
    
    node = OutputNode()
    
    if not node.start():
        print("Failed to start output node")
        return
        
    try:
        while True:
            print("\nServo Control Menu:")
            print("1. Test specific servo")
            print("2. Center all servos")
            print("3. Test range (min->center->max)")
            print("q. Quit")
            
            choice = input("\nEnter choice: ").strip().lower()
            
            if choice == 'q':
                break
                
            elif choice == '1':
                # Test specific servo
                try:
                    servo_id = int(input("Enter servo ID (1-8): "))
                    position = int(input("Enter position (500-2500): "))
                    
                    cmd = {
                        'type': 'servo',
                        'servo_id': servo_id,
                        'position': position,
                        'time_ms': 1000
                    }
                    
                    print(f"\nSending command: {cmd}")
                    response = node.handle_command(cmd)
                    print(f"Response: {response}")
                    
                except ValueError:
                    print("Invalid input! Please enter numbers only.")
                    
            elif choice == '2':
                # Center all servos
                print("\nCentering all servos...")
                for servo_id in range(1, 9):
                    cmd = {
                        'type': 'servo',
                        'servo_id': servo_id,
                        'position': 1500,  # Center position
                        'time_ms': 1000
                    }
                    response = node.handle_command(cmd)
                    print(f"Servo {servo_id}: {response}")
                    time.sleep(0.1)  # Small delay between servos
                    
            elif choice == '3':
                # Test range
                try:
                    servo_id = int(input("Enter servo ID (1-8): "))
                    
                    # Test sequence: min -> center -> max -> center
                    positions = [500, 1500, 2500, 1500]
                    for pos in positions:
                        cmd = {
                            'type': 'servo',
                            'servo_id': servo_id,
                            'position': pos,
                            'time_ms': 1000
                        }
                        print(f"\nMoving to position {pos}")
                        response = node.handle_command(cmd)
                        print(f"Response: {response}")
                        time.sleep(2)  # Wait between positions
                        
                except ValueError:
                    print("Invalid servo ID! Please enter a number between 1 and 8.")
            
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    finally:
        print("\nCentering all servos before exit...")
        # Center all servos before exit
        for servo_id in range(1, 9):
            node.handle_command({
                'type': 'servo',
                'servo_id': servo_id,
                'position': 1500,
                'time_ms': 1000
            })
            time.sleep(0.1)
        node.stop()

if __name__ == "__main__":
    test_servo_interactive() 