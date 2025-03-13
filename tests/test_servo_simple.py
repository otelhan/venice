#!/usr/bin/env python

import os
import sys
from pathlib import Path
import glob
import serial
import serial.tools.list_ports
import time
import yaml

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
    # Each unit = 0.12 degrees for servo mode
    units = int(1500 + (degrees * (1000/150)))
    return max(500, min(2500, units))

def units_to_degrees(units):
    """Convert servo units to degrees"""
    return (units - 1500) * 0.12

def speed_to_units(speed_percent):
    """Convert speed percentage (-100 to +100) to motor units"""
    # -100% = 500 (max CCW)
    # 0% = 1500 (stop)
    # +100% = 2500 (max CW)
    units = int(1500 + (speed_percent * 10))
    return max(500, min(2500, units))

def load_config():
    """Load servo configuration"""
    config_path = os.path.join(project_root, 'config', 'controllers.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def save_position(config, servo_id, angle):
    """Save servo position in degrees to config file"""
    config['servo_config']['servos'][str(servo_id)]['last_position_deg'] = angle
    
    config_path = os.path.join(project_root, 'config', 'controllers.yaml')
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

def test_servos():
    # Load config
    config = load_config()
    servo_config = config['servo_config']
    default_speed = servo_config.get('default_speed_ms', 1000)
    default_accel = servo_config.get('default_accel', 50)
    
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
        print("1. Move servo to angle")
        print("2. Center all servos (0°)")
        print("3. Read positions")
        print("4. Scan for connected servos")
        print("5. Set motor speed")
        print("6. Stop all motors")
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
                
                servo_config = config['servo_config']['servos'][str(servo_id)]
                if servo_config['mode'] != 'servo':
                    print(f"Servo {servo_id} is in motor mode! Use option 5 to control speed.")
                    continue
                    
                min_angle = servo_config.get('min_angle', -150)
                max_angle = servo_config.get('max_angle', 150)
                last_pos = servo_config.get('last_position_deg', 0)
                
                print(f"Current position: {last_pos:.1f}°")
                print(f"Valid range: {min_angle}° to {max_angle}°")
                
                degrees = float(input(f"Enter angle in degrees ({min_angle} to {max_angle}): "))
                if not min_angle <= degrees <= max_angle:
                    print("Invalid angle")
                    continue
                
                position = degrees_to_units(degrees)
                print(f"Moving to {degrees}° (units: {position})")
                
                speed = int(input(f"Enter time in ms (20-10000, default {default_speed}): ") or str(default_speed))
                accel = int(input(f"Enter acceleration (0-255, default {default_accel}): ") or str(default_accel))
                
                result, error = packetHandler.WritePosEx(servo_id, position, speed, accel)
                if result == COMM_SUCCESS:
                    print("Command sent successfully")
                    time.sleep(0.1)
                    pos, spd, result, error = packetHandler.ReadPosSpeed(servo_id)
                    if result == COMM_SUCCESS:
                        actual_degrees = units_to_degrees(pos)
                        print(f"Current position: {actual_degrees:.1f}°")
                        if servo_config.get('save_positions', True):
                            save_position(config, servo_id, actual_degrees)
                else:
                    print(f"Failed to move servo: {packetHandler.getTxRxResult(result)}")
                    
            except ValueError:
                print("Invalid input")
                
        elif choice == '2':
            print("Centering all servos (0°)...")
            for id in range(1, 6):
                result, error = packetHandler.WritePosEx(id, 1500, default_speed, default_accel)
                if result == COMM_SUCCESS:
                    print(f"Centered servo {id}")
                    if servo_config.get('save_positions', True):
                        save_position(config, id, 0.0)
                else:
                    print(f"Failed to center servo {id}")
                time.sleep(0.1)
                
        elif choice == '3':
            print("\nReading positions:")
            for id in range(1, 6):
                pos, spd, result, error = packetHandler.ReadPosSpeed(id)
                if result == COMM_SUCCESS:
                    degrees = units_to_degrees(pos)
                    print(f"Servo {id}: {degrees:.1f}° (units: {pos})")
                    if servo_config.get('save_positions', True):
                        save_position(config, id, degrees)
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
                        degrees = units_to_degrees(pos)
                        print(f"  Position: {degrees:.1f}°")
                        print(f"  Speed: {spd}")
                        if servo_config.get('save_positions', True):
                            save_position(config, id, degrees)
                else:
                    print(f"No response from servo {id}")
                
        elif choice == '5':  # Motor Speed Control
            try:
                servo_id = int(input("Enter servo ID (1-5): "))
                if not 1 <= servo_id <= 5:
                    print("Invalid servo ID")
                    continue
                    
                servo_config = config['servo_config']['servos'][str(servo_id)]
                if servo_config['mode'] != 'motor':
                    print(f"Servo {servo_id} is in servo mode! Use option 1 to control position.")
                    continue
                
                print("Speed: -100% (max CCW) to +100% (max CW), 0 = stop")
                speed_percent = float(input("Enter speed percentage: "))
                if not -100 <= speed_percent <= 100:
                    print("Invalid speed")
                    continue
                
                position = speed_to_units(speed_percent)
                print(f"Setting speed to {speed_percent}% (units: {position})")
                
                result, error = packetHandler.WritePosEx(servo_id, position, default_speed, default_accel)
                if result == COMM_SUCCESS:
                    print("Command sent successfully")
                else:
                    print(f"Failed to set speed: {packetHandler.getTxRxResult(result)}")
                    
            except ValueError:
                print("Invalid input")
                
        elif choice == '6':  # Stop All Motors
            print("Stopping all motors...")
            for id in range(1, 6):
                servo_config = config['servo_config']['servos'][str(id)]
                if servo_config['mode'] == 'motor':
                    result, error = packetHandler.WritePosEx(id, 1500, default_speed, default_accel)
                    if result == COMM_SUCCESS:
                        print(f"Stopped motor {id}")
                    else:
                        print(f"Failed to stop motor {id}")
                time.sleep(0.1)

    # Close port
    portHandler.closePort()

if __name__ == "__main__":
    test_servos() 