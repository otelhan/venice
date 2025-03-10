#!/usr/bin/env python

import os
import sys
from pathlib import Path

# Get project root directory
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Import from the correct directory
from lib.STservo_sdk.sts import *
from lib.STservo_sdk.port_handler import PortHandler
import time
import glob

def find_servos(port="/dev/tty.usbserial", baud=1000000):
    """Find all connected servos and return their IDs"""
    print("\nScanning for servos...")
    
    # Initialize handlers
    port_handler = PortHandler(port)
    packet_handler = sts(port_handler)
    
    # Open port
    if not port_handler.openPort():
        print(f"Failed to open port {port}")
        return []
        
    # Set port baudrate
    if not port_handler.setBaudRate(baud):
        print(f"Failed to change baudrate to {baud}")
        return []
        
    found_servos = []
    
    # Scan through possible IDs
    for servo_id in range(1, 9):
        print(f"\nPinging servo ID {servo_id}...")
        model_number, comm_result, error = packet_handler.ping(servo_id)
        
        if comm_result == COMM_SUCCESS:
            print(f"Found servo ID: {servo_id}")
            print(f"Model number: {model_number}")
            
            # Read current position
            position, speed, comm_result, error = packet_handler.ReadPosSpeed(servo_id)
            if comm_result == COMM_SUCCESS:
                print(f"Current position: {position}")
                print(f"Current speed: {speed}")
            
            found_servos.append(servo_id)
        else:
            print(f"Failed to ping servo {servo_id}")
            
    return found_servos

def test_servo_sdk():
    """Test servos using SDK"""
    print("\nServo SDK Test")
    print("-------------")
    
    # Mac port naming patterns
    ports = [
        "/dev/tty.usbserial*",        # Most common for USB-Serial adapters
        "/dev/tty.SLAB_USBtoUART*",   # Silicon Labs adapter
        "/dev/tty.wchusbserial*",     # CH340 adapter
        "/dev/tty.usbmodem*"          # Native USB
    ]
    
    # Expand globs to actual ports
    actual_ports = []
    for pattern in ports:
        actual_ports.extend(glob.glob(pattern))
        
    if not actual_ports:
        print("No serial ports found! Available ports:")
        import serial.tools.list_ports
        for port in serial.tools.list_ports.comports():
            print(f"  {port.device} - {port.description}")
        return
        
    print("\nFound ports:", actual_ports)
    
    baud_rates = [1000000, 115200, 9600]  # Added 9600 for testing
    
    found_servos = []
    active_port = None
    active_baud = None
    
    for port in actual_ports:
        for baud in baud_rates:
            print(f"\nTrying {port} at {baud} baud...")
            found = find_servos(port, baud)
            if found:
                print(f"\nFound servos on {port} at {baud} baud!")
                found_servos = found
                active_port = port
                active_baud = baud
                break
        if found_servos:
            break
            
    if not found_servos:
        print("No servos found!")
        return
        
    print(f"\nFound {len(found_servos)} servos: {found_servos}")
    
    # Initialize for control
    port_handler = PortHandler(active_port)
    packet_handler = sts(port_handler)
    
    if not port_handler.openPort() or not port_handler.setBaudRate(active_baud):
        print("Failed to open port for control")
        return
        
    try:
        while True:
            print("\nServo Control Menu:")
            print("1. Test specific servo")
            print("2. Center all servos")
            print("3. Read positions")
            print("4. Test all 5 servos sequence")
            print("q. Quit")
            
            choice = input("\nEnter choice: ").strip().lower()
            
            if choice == 'q':
                break
                
            elif choice == '1':
                try:
                    servo_id = int(input("Enter servo ID (1-5): "))
                    if servo_id not in range(1, 6):
                        print("Invalid servo ID! Must be between 1 and 5")
                        continue
                        
                    position = int(input("Enter position (500-2500): "))
                    if not (500 <= position <= 2500):
                        print("Invalid position! Must be between 500 and 2500")
                        continue
                    
                    # Move servo
                    result, error = packet_handler.WritePosEx(servo_id, position, 100, 50)
                    if result == COMM_SUCCESS:
                        print("Command sent successfully")
                        # Read back position
                        time.sleep(1)
                        pos, spd, result, error = packet_handler.ReadPosSpeed(servo_id)
                        if result == COMM_SUCCESS:
                            print(f"New position: {pos}")
                    else:
                        print(f"Failed to send command: {packet_handler.getTxRxResult(result)}")
                        
                except ValueError:
                    print("Invalid input!")
                    
            elif choice == '2':
                print("\nCentering all servos...")
                for servo_id in range(1, 6):
                    result, error = packet_handler.WritePosEx(servo_id, 1500, 100, 50)
                    if result != COMM_SUCCESS:
                        print(f"Failed to center servo {servo_id}")
                    time.sleep(0.1)
                    
            elif choice == '3':
                print("\nReading positions:")
                for servo_id in range(1, 6):
                    pos, spd, result, error = packet_handler.ReadPosSpeed(servo_id)
                    if result == COMM_SUCCESS:
                        print(f"Servo {servo_id}: Position={pos}, Speed={spd}")
                    else:
                        print(f"Failed to read servo {servo_id}")
                        
            elif choice == '4':
                print("\nTesting all 5 servos in sequence...")
                positions = [500, 1500, 2500, 1500]
                
                for servo_id in range(1, 6):
                    print(f"\nTesting Servo {servo_id}")
                    for pos in positions:
                        print(f"Moving to position {pos}")
                        result, error = packet_handler.WritePosEx(servo_id, pos, 100, 50)
                        if result == COMM_SUCCESS:
                            print("Command sent successfully")
                            time.sleep(1)
                            pos_actual, spd, result, error = packet_handler.ReadPosSpeed(servo_id)
                            if result == COMM_SUCCESS:
                                print(f"Current position: {pos_actual}")
                        else:
                            print(f"Failed to move servo {servo_id}")
                        time.sleep(1)
                    
                    packet_handler.WritePosEx(servo_id, 1500, 100, 50)
                    time.sleep(1)
                    
    except KeyboardInterrupt:
        print("\nTest interrupted")
    finally:
        port_handler.closePort()

if __name__ == "__main__":
    test_servo_sdk() 