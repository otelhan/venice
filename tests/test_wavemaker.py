import serial
import time

def test_wavemaker():
    """Test wavemaker control"""
    print("\nWavemaker Control Test")
    print("---------------------")
    
    # Try different possible ports on Raspberry Pi
    ports = [
        '/dev/ttyACM0',
        '/dev/ttyACM1',
        '/dev/ttyUSB0',
        '/dev/ttyUSB1'
    ]
    
    # List available ports
    print("\nAvailable ports:")
    for port in ports:
        try:
            serial.Serial(port)
            print(f"- {port} (available)")
        except:
            print(f"- {port} (not available)")
    
    # Connect to port
    port = input("\nEnter port to use (e.g. /dev/ttyACM0): ").strip()
    
    try:
        print(f"\nConnecting to {port}...")
        # Set a shorter timeout to prevent hanging
        serial_port = serial.Serial(port, 9600, timeout=2)
        print("Connected!")
        
        # Wait for device ready and clear any startup messages
        time.sleep(2)
        if serial_port.in_waiting:
            startup = serial_port.readline().decode().strip()
            print(f"Startup message: {startup}")
        
        while True:
            print("\nCommands:")
            print("1. Turn ON")
            print("2. Turn OFF")
            print("3. Set speed (20-127)")
            print("4. Run test sequence")
            print("q. Quit")
            
            cmd = input("\nEnter command: ").strip().lower()
            
            if cmd == 'q':
                break
            elif cmd == '1':
                print("Sending: on")
                serial_port.write(b"on\n")
                serial_port.flush()
                try:
                    response = serial_port.readline()
                    if response:
                        print(f"Response: {response.decode().strip()}")
                    else:
                        print("No response received (timeout)")
                except Exception as e:
                    print(f"Error reading response: {e}")
            elif cmd == '2':
                print("Sending: off")
                serial_port.write(b"off\n")
                serial_port.flush()
                try:
                    response = serial_port.readline()
                    if response:
                        print(f"Response: {response.decode().strip()}")
                    else:
                        print("No response received (timeout)")
                except Exception as e:
                    print(f"Error reading response: {e}")
            elif cmd == '3':
                speed = input("Enter speed (20-127): ").strip()
                try:
                    speed_val = int(speed)
                    if 20 <= speed_val <= 127:
                        print(f"Sending: {speed}")
                        serial_port.write(f"{speed}\n".encode())
                        serial_port.flush()
                        try:
                            response = serial_port.readline()
                            if response:
                                print(f"Response: {response.decode().strip()}")
                            else:
                                print("No response received (timeout)")
                        except Exception as e:
                            print(f"Error reading response: {e}")
                    else:
                        print("Speed must be between 20 and 127")
                except ValueError:
                    print("Invalid speed value")
            elif cmd == '4':
                print("\nRunning test sequence...")
                # Turn on
                serial_port.write(b"on\n")
                print(f"Response: {serial_port.readline().decode().strip()}")
                time.sleep(1)
                
                # Test different speeds
                test_speeds = [20, 50, 80, 127]
                for speed in test_speeds:
                    print(f"\nTesting speed: {speed}")
                    serial_port.write(f"{speed}\n".encode())
                    print(f"Response: {serial_port.readline().decode().strip()}")
                    time.sleep(2)
                
                # Turn off
                serial_port.write(b"off\n")
                print(f"Response: {serial_port.readline().decode().strip()}")
    
    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        if 'serial_port' in locals():
            serial_port.close()
            print("\nSerial port closed")

if __name__ == "__main__":
    try:
        test_wavemaker()
    except KeyboardInterrupt:
        print("\nProgram terminated by user") 