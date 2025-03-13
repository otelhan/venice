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

def find_ports():
    """Find all available serial ports"""
    print("\nScanning for available ports...")
    
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No ports found!")
        return []
        
    print("\nAvailable ports:")
    for i, port in enumerate(ports):
        print(f"{i+1}: {port.device} - {port.description}")
    
    selected_ports = []
    while True:
        choice = input("\nSelect port number (Enter to finish): ").strip()
        if not choice:
            break
            
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                selected_ports.append(ports[idx].device)
                print(f"Added: {ports[idx].device}")
            else:
                print("Invalid selection")
        except ValueError:
            print("Invalid input")
            
    return selected_ports

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

class ServoController:
    def __init__(self, port):
        self.port = port
        self.port_handler = PortHandler(port)
        self.packet_handler = sts(self.port_handler)
        
    def connect(self):
        if self.port_handler.openPort():
            print(f"Succeeded to open {self.port}")
            if self.port_handler.setBaudRate(1000000):
                print("Succeeded to change baudrate")
                return True
        return False
        
    def close(self):
        self.port_handler.closePort()

def test_servos():
    # Load config
    config = load_config()
    servo_config = config['servo_config']
    default_speed = servo_config.get('default_speed_ms', 1000)
    default_accel = servo_config.get('default_accel', 50)
    
    # Find and connect to controllers
    ports = find_ports()
    if not ports:
        print("No ports selected")
        return
        
    controllers = []
    for port in ports:
        controller = ServoController(port)
        if controller.connect():
            controllers.append(controller)
        else:
            print(f"Failed to connect to {port}")
    
    if not controllers:
        print("No controllers connected")
        return

    while True:
        print("\nServo Test Menu:")
        print("1. Move servo to angle")
        print("2. Center all servos")
        print("3. Read positions")
        print("4. Scan for connected servos")
        print("c. Select controller")
        print("q. Quit")
        
        choice = input("Select option: ").strip().lower()
        
        if choice == 'q':
            break
            
        elif choice == 'c':
            print("\nAvailable controllers:")
            for i, ctrl in enumerate(controllers):
                print(f"{i+1}: {ctrl.port}")
            try:
                idx = int(input("Select controller: ")) - 1
                if 0 <= idx < len(controllers):
                    active_controller = controllers[idx]
                    print(f"Selected: {active_controller.port}")
                else:
                    print("Invalid selection")
            except ValueError:
                print("Invalid input")
                
        elif choice == '1':
            try:
                servo_id = int(input("Enter servo ID (1-5): "))
                if not 1 <= servo_id <= 5:
                    print("Invalid servo ID")
                    continue
                
                servo_config = config['servo_config']['servos'][str(servo_id)]
                min_angle = servo_config.get('min_angle', -150)
                max_angle = servo_config.get('max_angle', 150)
                
                degrees = float(input(f"Enter angle in degrees ({min_angle} to {max_angle}): "))
                if not min_angle <= degrees <= max_angle:
                    print("Invalid angle")
                    continue
                
                position = degrees_to_units(degrees)
                print(f"Moving to {degrees}° (units: {position})")
                
                speed = int(input(f"Enter time in ms (20-10000, default {default_speed}): ") or str(default_speed))
                accel = int(input(f"Enter acceleration (0-255, default {default_accel}): ") or str(default_accel))
                
                result, error = active_controller.packet_handler.WritePosEx(servo_id, position, speed, accel)
                if result == COMM_SUCCESS:
                    print("Command sent successfully")
                else:
                    print(f"Failed to move servo: {active_controller.packet_handler.getTxRxResult(result)}")
                    
            except ValueError:
                print("Invalid input")
                
        elif choice == '2':
            print("Centering all servos (0°)...")
            for id in range(1, 6):
                result, error = active_controller.packet_handler.WritePosEx(id, 1500, default_speed, default_accel)
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
                pos, spd, result, error = active_controller.packet_handler.ReadPosSpeed(id)
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
                model_number, result, error = active_controller.packet_handler.ping(id)
                if result == COMM_SUCCESS:
                    print(f"Found servo {id}")
                    pos, spd, result, error = active_controller.packet_handler.ReadPosSpeed(id)
                    if result == COMM_SUCCESS:
                        degrees = units_to_degrees(pos)
                        print(f"  Position: {degrees:.1f}°")
                        print(f"  Speed: {spd}")
                        if servo_config.get('save_positions', True):
                            save_position(config, id, degrees)
                else:
                    print(f"No response from servo {id}")

    # Close all controllers
    for controller in controllers:
        controller.close()

if __name__ == "__main__":
    test_servos() 