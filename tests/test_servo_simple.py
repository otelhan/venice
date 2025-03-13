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

class ServoController:
    def __init__(self, port, baud=1000000):
        self.port = port
        self.baud = baud
        self.port_handler = PortHandler(port)
        self.packet_handler = sts(self.port_handler)
        
    def connect(self):
        if self.port_handler.openPort():
            print(f"Opened port {self.port}")
            if self.port_handler.setBaudRate(self.baud):
                print("Set baud rate successfully")
                return True
        return False
        
    def close(self):
        self.port_handler.closePort()

def find_controllers():
    """Find and setup multiple controllers"""
    print("\nScanning for available ports...")
    
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No ports found!")
        return {}
        
    print("\nAvailable ports:")
    for i, port in enumerate(ports):
        print(f"{i+1}: {port.device} - {port.description}")
        
    controllers = {}
    
    # Select main controller
    print("\nSelect MAIN controller (5 servos):")
    main_port = select_port(ports)
    if main_port:
        controllers['main'] = ServoController(main_port)
        
    # Select secondary controller
    print("\nSelect SECONDARY controller (mirror servo):")
    secondary_port = select_port(ports)
    if secondary_port:
        controllers['secondary'] = ServoController(secondary_port)
        
    return controllers

def select_port(ports):
    """Helper to select a port from list"""
    try:
        choice = int(input("Select port number (or 0 to skip): ").strip())
        if 1 <= choice <= len(ports):
            return ports[choice-1].device
    except ValueError:
        pass
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

def save_position(config, controller_key, servo_id, angle):
    """Save servo position in degrees to config file"""
    config['servo_config']['controllers'][controller_key]['servos'][str(servo_id)]['last_position_deg'] = angle
    
    config_path = os.path.join(project_root, 'config', 'controllers.yaml')
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

def test_servos():
    # Load config
    config = load_config()
    servo_config = config['servo_config']
    default_speed = servo_config.get('default_speed_ms', 1000)  # Get from top level
    default_accel = servo_config.get('default_accel', 50)      # Get from top level
    
    # Find and connect to controllers
    controllers = find_controllers()
    if not controllers:
        print("No controllers connected")
        return
        
    # Connect all controllers
    for name, controller in controllers.items():
        if not controller.connect():
            print(f"Failed to connect to {name} controller")
            return
            
    while True:
        print("\nServo Test Menu:")
        print("1. Move servo to angle")
        print("2. Center all servos")
        print("3. Read positions")
        print("4. Scan for connected servos")
        print("5. Set motor speed")
        print("6. Stop all motors")
        print("q. Quit")
        
        choice = input("Select option: ").strip().lower()
        
        if choice == 'q':
            break
            
        elif choice == '1':
            # Select controller
            print("\nSelect controller:")
            print("1. Main (5 servos)")
            print("2. Secondary (mirror servo)")
            
            try:
                ctrl_choice = input("Controller (1-2): ").strip()
                controller = controllers['main'] if ctrl_choice == '1' else controllers['secondary']
                config_key = 'main' if ctrl_choice == '1' else 'secondary'
                
                # Get servo ID (1-5 for main, only 1 for secondary)
                max_id = 5 if ctrl_choice == '1' else 1
                servo_id = int(input(f"Enter servo ID (1-{max_id}): "))
                if not 1 <= servo_id <= max_id:
                    print("Invalid servo ID")
                    continue
                
                servo_config = config['servo_config']['controllers'][config_key]['servos'][str(servo_id)]
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
                
                result, error = controller.packet_handler.WritePosEx(servo_id, position, speed, accel)
                if result == COMM_SUCCESS:
                    print(f"Command sent successfully to {controller.port}")
                    print(f"  Servo ID: {servo_id}")
                    print(f"  Position: {position}")
                    print(f"  Speed: {speed}")
                    print(f"  Accel: {accel}")
                    time.sleep(0.1)
                    pos, spd, result, error = controller.packet_handler.ReadPosSpeed(servo_id)
                    if result == COMM_SUCCESS:
                        actual_degrees = units_to_degrees(pos)
                        print(f"Current position: {actual_degrees:.1f}°")
                        if servo_config.get('save_positions', True):
                            save_position(config, config_key, servo_id, actual_degrees)
                else:
                    print(f"Failed to move servo: {controller.packet_handler.getTxRxResult(result)}")
                    print(f"Error: {error}")
                    
            except (ValueError, KeyError):
                print("Invalid input")
                
        elif choice == '2':
            print("Centering all servos (0°)...")
            
            # Center main controller servos if connected
            if 'main' in controllers:
                print("\nCentering main controller servos...")
                for id in range(1, 6):
                    result, error = controllers['main'].packet_handler.WritePosEx(id, 1500, default_speed, default_accel)
                    if result == COMM_SUCCESS:
                        print(f"Centered servo {id}")
                        if servo_config.get('save_positions', True):
                            save_position(config, 'main', id, 0.0)
                    else:
                        print(f"Failed to center servo {id}")
                    time.sleep(0.1)
            
            # Center secondary controller servo if connected
            if 'secondary' in controllers:
                print("\nCentering secondary controller servo...")
                result, error = controllers['secondary'].packet_handler.WritePosEx(1, 1500, default_speed, default_accel)
                if result == COMM_SUCCESS:
                    print("Centered clock servo")
                    if servo_config.get('save_positions', True):
                        save_position(config, 'secondary', 1, 0.0)
                else:
                    print("Failed to center clock servo")
                time.sleep(0.1)
                
        elif choice == '3':
            print("\nReading positions:")
            for id in range(1, 6):
                pos, spd, result, error = controllers['main'].packet_handler.ReadPosSpeed(id)
                if result == COMM_SUCCESS:
                    degrees = units_to_degrees(pos)
                    print(f"Servo {id}: {degrees:.1f}° (units: {pos})")
                    if servo_config.get('save_positions', True):
                        save_position(config, 'main', id, degrees)
                else:
                    print(f"Failed to read servo {id}")
                    
        elif choice == '4':
            print("\nScanning for connected servos...")
            for id in range(1, 6):
                model_number, result, error = controllers['main'].packet_handler.ping(id)
                if result == COMM_SUCCESS:
                    print(f"Found servo {id}")
                    pos, spd, result, error = controllers['main'].packet_handler.ReadPosSpeed(id)
                    if result == COMM_SUCCESS:
                        degrees = units_to_degrees(pos)
                        print(f"  Position: {degrees:.1f}°")
                        print(f"  Speed: {spd}")
                        if servo_config.get('save_positions', True):
                            save_position(config, 'main', id, degrees)
                else:
                    print(f"No response from servo {id}")
                
        elif choice == '5':  # Motor Speed Control
            try:
                # Select controller
                print("\nSelect controller:")
                print("1. Main (5 servos)")
                print("2. Secondary (mirror servo)")
                
                ctrl_choice = input("Controller (1-2): ").strip()
                controller = controllers['main'] if ctrl_choice == '1' else controllers['secondary']
                config_key = 'main' if ctrl_choice == '1' else 'secondary'
                
                # Get servo ID (1-5 for main, only 1 for secondary)
                max_id = 5 if ctrl_choice == '1' else 1
                servo_id = int(input(f"Enter servo ID (1-{max_id}): "))
                if not 1 <= servo_id <= max_id:
                    print("Invalid servo ID")
                    continue
                    
                servo_config = config['servo_config']['controllers'][config_key]['servos'][str(servo_id)]
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
                
                result, error = controller.packet_handler.WritePosEx(servo_id, position, default_speed, default_accel)
                if result == COMM_SUCCESS:
                    print("Command sent successfully")
                else:
                    print(f"Failed to set speed: {controller.packet_handler.getTxRxResult(result)}")
                    
            except (ValueError, KeyError):
                print("Invalid input")
                
        elif choice == '6':  # Stop All Motors
            print("Stopping all motors...")
            for id in range(1, 6):
                servo_config = config['servo_config']['controllers']['main']['servos'][str(id)]
                if servo_config['mode'] == 'motor':
                    result, error = controllers['main'].packet_handler.WritePosEx(id, 1500, default_speed, default_accel)
                    if result == COMM_SUCCESS:
                        print(f"Stopped motor {id}")
                    else:
                        print(f"Failed to stop motor {id}")
                time.sleep(0.1)

    # Close all controllers
    for controller in controllers.values():
        controller.close()

if __name__ == "__main__":
    test_servos() 