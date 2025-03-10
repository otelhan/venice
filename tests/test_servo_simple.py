#!/usr/bin/env python

import os
import sys
from pathlib import Path
import glob
import serial
import serial.tools.list_ports
import time

# Get project root directory
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from lib.STservo_sdk.sts import *
from lib.STservo_sdk.port_handler import PortHandler

def find_port():
    """Find the correct serial port"""
    print("\nScanning for available ports...")
    
    # List all ports
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No ports found!")
        return None
        
    print("\nAvailable ports:")
    for i, port in enumerate(ports):
        print(f"{i+1}: {port.device} - {port.description}")
        
    # Let user choose
    try:
        choice = int(input("\nSelect port number: ").strip())
        if 1 <= choice <= len(ports):
            selected_port = ports[choice-1].device
            print(f"Selected: {selected_port}")
            return selected_port
    except ValueError:
        pass
        
    print("Invalid selection")
    return None

def degrees_to_units(degrees):
    """Convert degrees to servo units (500-2500)"""
    # 1500 is center (0 degrees)
    # Each unit = 0.24 degrees
    units = int(1500 + (degrees * (1000/240)))
    return max(500, min(2500, units))  # Clamp to valid range

def units_to_degrees(units):
    """Convert servo units to degrees"""
    return (units - 1500) * 0.24

def test_servos():
    # Find and open port
    port = find_port()
    if not port:
        print("No port selected")
        return
        
    # Initialize handlers with selected port
    portHandler = PortHandler(port)
    packetHandler = sts(portHandler)
    
    # Open port
    if portHandler.openPort():
        print("Succeeded to open the port")
    else:
        print("Failed to open the port")
        return

    # Set port baudrate
    if portHandler.setBaudRate(1000000):
        print("Succeeded to change the baudrate")
    else:
        print("Failed to change the baudrate")
        return

    while True:
        print("\nServo Test Menu:")
        print("1. Test single servo")
        print("2. Center all servos")
        print("3. Read positions")
        print("4. Scan for connected servos")
        print("5. Move to angle")  # New option
        print("q. Quit")
        
        choice = input("Select option: ").strip().lower()
        
        if choice == 'q':
            break
            
        elif choice == '1':
            try:
                servo_id = int(input("Enter servo ID (1-5): "))
                if not 1 <= servo_id <= 5:
                    print("Invalid servo ID")
                    continue
                    
                position = int(input("Enter position (500-2500): "))
                if not 500 <= position <= 2500:
                    print("Invalid position")
                    continue
                
                # Speed is actually time in milliseconds (lower = faster)
                speed = int(input("Enter time in ms (20-10000, default 1000): ") or "1000")
                if not 20 <= speed <= 10000:
                    print("Invalid time value")
                    continue
                    
                # Acceleration (0-255)
                accel = int(input("Enter acceleration (0-255, default 50): ") or "50")
                if not 0 <= accel <= 255:
                    print("Invalid acceleration")
                    continue
                
                # Write goal position
                result, error = packetHandler.WritePosEx(servo_id, position, speed, accel)
                if result != COMM_SUCCESS:
                    print("%s" % packetHandler.getTxRxResult(result))
                else:
                    print(f"Command sent successfully - Time: {speed}ms, Accel: {accel}")
            except ValueError:
                print("Invalid input")
            
        elif choice == '2':
            print("Centering all servos...")
            for id in range(1, 6):
                result, error = packetHandler.WritePosEx(id, 1500, 100, 50)
                if result == COMM_SUCCESS:
                    print(f"Centered servo {id}")
                else:
                    print(f"Failed to center servo {id}")
                time.sleep(0.1)
                
        elif choice == '3':
            print("\nReading positions:")
            for id in range(1, 6):
                pos, spd, result, error = packetHandler.ReadPosSpeed(id)
                if result == COMM_SUCCESS:
                    print(f"Servo {id}: Position={pos}, Speed={spd}")
                else:
                    print(f"Failed to read servo {id}")
                    
        elif choice == '4':
            print("\nScanning for connected servos...")
            for id in range(1, 6):
                model_number, result, error = packetHandler.ping(id)
                if result == COMM_SUCCESS:
                    print(f"Found servo {id}")
                    pos, spd, result, error = packetHandler.ReadPosSpeed(id)
                    if result == COMM_SUCCESS:
                        print(f"  Position: {pos}")
                        print(f"  Speed: {spd}")
                else:
                    print(f"No response from servo {id}")

        elif choice == '5':
            try:
                servo_id = int(input("Enter servo ID (1-5): "))
                if not 1 <= servo_id <= 5:
                    print("Invalid servo ID")
                    continue
                    
                degrees = float(input("Enter angle in degrees (-240 to +240): "))
                if not -240 <= degrees <= 240:
                    print("Invalid angle")
                    continue
                
                position = degrees_to_units(degrees)
                print(f"Moving to {degrees}° (units: {position})")
                
                speed = int(input("Enter time in ms (20-10000, default 1000): ") or "1000")
                accel = int(input("Enter acceleration (0-255, default 50): ") or "50")
                
                result, error = packetHandler.WritePosEx(servo_id, position, speed, accel)
                if result == COMM_SUCCESS:
                    print("Command sent successfully")
                    time.sleep(1)
                    # Read back actual position
                    pos, spd, result, error = packetHandler.ReadPosSpeed(servo_id)
                    if result == COMM_SUCCESS:
                        actual_degrees = units_to_degrees(pos)
                        print(f"Current position: {actual_degrees:.1f}°")
                else:
                    print(f"Failed to move servo: {packetHandler.getTxRxResult(result)}")
                    
            except ValueError:
                print("Invalid input")

    # Close port
    portHandler.closePort()

if __name__ == "__main__":
    test_servos() 