import serial
import time
import glob

def send_command(serial_port, cmd, wait_time=1):
    """Send command and wait for response"""
    print(f"\nSending: {cmd}")
    
    # Clear any pending data
    serial_port.reset_input_buffer()
    serial_port.reset_output_buffer()
    
    # Send command
    serial_port.write(f"{cmd}\n".encode())
    serial_port.flush()
    
    # Wait for response
    response = serial_port.readline().decode().strip()
    print(f"Response: {response}")
    time.sleep(wait_time)
    return response

def test_wavemaker():
    """Test wavemaker control"""
    print("\nWavemaker Control Test")
    print("---------------------")
    
    # Try different possible ports
    ports = [
        '/dev/ttyACM0',        # Linux/Raspberry Pi
        '/dev/ttyACM1',
        '/dev/ttyUSB0',
        '/dev/ttyUSB1',
        'COM3',                # Windows
        'COM4',
        '/dev/tty.usbmodem*'   # Mac
    ]
    
    # List available ports
    available_ports = []
    for pattern in ports:
        available_ports.extend(glob.glob(pattern))
    
    print("\nAvailable ports:")
    for port in available_ports:
        print(f"- {port}")
    
    # Connect to first available port
    serial_port = None
    for port in available_ports:
        try:
            print(f"\nTrying to connect to {port}...")
            serial_port = serial.Serial(port, 9600, timeout=1)
            print(f"Connected to {port}")
            break
        except serial.SerialException as e:
            print(f"Failed to connect to {port}: {e}")
            continue
    
    if not serial_port:
        print("ERROR: Could not connect to wavemaker!")
        return
    
    try:
        # Wait for device ready
        time.sleep(2)
        serial_port.reset_input_buffer()
        
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
                send_command(serial_port, "on")
            elif cmd == '2':
                send_command(serial_port, "off")
            elif cmd == '3':
                speed = input("Enter speed (20-127): ").strip()
                try:
                    speed_val = int(speed)
                    if 20 <= speed_val <= 127:
                        send_command(serial_port, str(speed_val))
                    else:
                        print("Speed must be between 20 and 127")
                except ValueError:
                    print("Invalid speed value")
            elif cmd == '4':
                print("\nRunning test sequence...")
                # Turn on
                send_command(serial_port, "on")
                time.sleep(1)
                
                # Test different speeds
                test_speeds = [20, 50, 80, 127]
                for speed in test_speeds:
                    print(f"\nTesting speed: {speed}")
                    send_command(serial_port, str(speed))
                    time.sleep(2)
                
                # Turn off
                send_command(serial_port, "off")
            else:
                print("Invalid command")
    
    except Exception as e:
        print(f"Error during test: {e}")
    
    finally:
        if serial_port:
            serial_port.close()
            print("\nSerial port closed")

if __name__ == "__main__":
    test_wavemaker() 