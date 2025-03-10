import time
from src.networking.output_node import OutputNode, ServoController
import glob
import serial

def find_servo_port():
    """Find the correct servo port"""
    print("\nScanning for servo board...")
    
    # Try different possible ports and baud rates
    ports = [
        '/dev/ttyACM0',
        '/dev/ttyACM1',
        '/dev/ttyUSB0',
        '/dev/ttyUSB1'
    ]
    
    baud_rates = [115200, 9600, 1000000]
    
    for port in ports:
        for baud in baud_rates:
            try:
                s = serial.Serial(port, baud, timeout=1)
                print(f"Found potential board on {port} at {baud} baud")
                s.close()
                return port, baud
            except:
                continue
                
    print("No servo board found!")
    return None, None

def test_servo_interactive():
    """Interactive servo testing"""
    print("\nServo Control Test")
    print("-----------------")
    
    # Find the correct port first
    port, baud = find_servo_port()
    if not port:
        print("Could not find servo board!")
        return
        
    print(f"Using port: {port} at {baud} baud")
    node = OutputNode()
    node.servo_controller.port = port
    node.servo_controller.baud = baud
    
    if not node.start():
        print("Failed to start output node")
        return
        
    try:
        while True:
            print("\nServo Control Menu:")
            print("1. Test specific servo")
            print("2. Center all servos")
            print("3. Test range (min->center->max)")
            print("4. Scan for connected servos")  # New option
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
                        'position': 1500,
                        'time_ms': 1000
                    }
                    response = node.handle_command(cmd)
                    print(f"Servo {servo_id}: {response}")
                    time.sleep(0.1)
                    
            elif choice == '3':
                # Test range
                try:
                    servo_id = int(input("Enter servo ID (1-8): "))
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
                        time.sleep(2)
                        
                except ValueError:
                    print("Invalid servo ID! Please enter a number between 1 and 8.")
                    
            elif choice == '4':
                # Scan for connected servos
                print("\nScanning for connected servos...")
                for servo_id in range(1, 9):
                    cmd = {
                        'type': 'servo',
                        'servo_id': servo_id,
                        'position': 1500,
                        'time_ms': 500
                    }
                    response = node.handle_command(cmd)
                    if response['status'] == 'ok':
                        print(f"Servo {servo_id}: Connected")
                    time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    finally:
        print("\nCentering all servos before exit...")
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