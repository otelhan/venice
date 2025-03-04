import serial
import time
import sys
import glob

def get_serial_ports():
    """Get list of available serial ports for current platform"""
    if sys.platform.startswith('darwin'):  # macOS
        ports = glob.glob('/dev/tty.*')
        # Common Mac port patterns
        return [p for p in ports if any(pattern in p for pattern in 
               ['usbmodem', 'usbserial', 'SLAB_USBtoUART'])]
    
    elif sys.platform.startswith('linux'):  # Linux/Raspberry Pi
        return [
            '/dev/ttyACM0',
            '/dev/ttyACM1',
            '/dev/ttyUSB0',
            '/dev/ttyUSB1'
        ]
    else:
        return []  # Add Windows support if needed

def test_wavemaker():
    """Test wavemaker control"""
    print("\nWavemaker Control Test")
    print("---------------------")
    
    # Get available ports for current platform
    ports = get_serial_ports()
    
    # List available ports
    print("\nScanning available ports...")
    available_ports = []
    for port in ports:
        try:
            s = serial.Serial(port, timeout=0.1)
            s.close()
            available_ports.append(port)
            print(f"- {port} (available)")
        except:
            print(f"- {port} (not available)")
    
    if not available_ports:
        print("\nNo available ports found!")
        return
    
    # Connect to port
    if len(available_ports) == 1:
        port = available_ports[0]
        print(f"\nUsing only available port: {port}")
    else:
        print("\nMultiple ports available. Please select one:")
        for i, port in enumerate(available_ports):
            print(f"{i+1}. {port}")
        while True:
            try:
                choice = int(input("\nEnter port number: ").strip())
                if 1 <= choice <= len(available_ports):
                    port = available_ports[choice-1]
                    break
                print("Invalid choice")
            except ValueError:
                print("Please enter a number")
    
    try:
        print(f"\nConnecting to {port}...")
        serial_port = serial.Serial(port, 9600, timeout=2)
        print("Connected!")
        
        # Clear any startup messages
        time.sleep(2)
        while serial_port.in_waiting:
            print(f"Startup: {serial_port.readline().decode().strip()}")
        
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
                print("\nSending: on")
                serial_port.write(b"on\n")
                serial_port.flush()
                time.sleep(0.5)  # Give device time to respond
                
                # Read and clear any pending data
                while serial_port.in_waiting:
                    response = serial_port.readline().decode().strip()
                    print(f"Response: {response}")
                print("Ready for next command...")
                
            elif cmd == '2':
                print("\nSending: off")
                serial_port.write(b"off\n")
                serial_port.flush()
                time.sleep(0.5)
                
                while serial_port.in_waiting:
                    response = serial_port.readline().decode().strip()
                    print(f"Response: {response}")
                    
            elif cmd == '3':
                speed = input("Enter speed (20-127): ").strip()
                try:
                    speed_val = int(speed)
                    if 20 <= speed_val <= 127:
                        print(f"\nSending: {speed}")
                        serial_port.write(f"{speed}\n".encode())
                        serial_port.flush()
                        time.sleep(0.5)
                        
                        while serial_port.in_waiting:
                            response = serial_port.readline().decode().strip()
                            print(f"Response: {response}")
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