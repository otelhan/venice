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
        
        # Set configuration based on model
        if 'ACM0' in port:
            self.servo_count = 5
            self.model = "ST3020"
            self.default_speed = 100  # Default for ST3020
            self.default_accel = 50
        else:
            self.servo_count = 1
            self.model = "ST3215"
            self.default_speed = 500  # Slower default for ST3215 (more precise)
            self.default_accel = 30   # Lower acceleration for smoother movement
            
    def connect(self):
        if self.port_handler.openPort():
            print(f"Succeeded to open {self.port} ({self.servo_count} servos, {self.model})")
            if self.port_handler.setBaudRate(1000000):
                print("Succeeded to change baudrate")
                return True
        return False
        
    def write_position(self, servo_id, position, speed, accel):
        """Write position with timeout"""
        try:
            # Add delay for ST3215 to ensure command is processed
            if self.model == "ST3215":
                time.sleep(0.02)  # 20ms delay
                
            result, error = self.packet_handler.WritePosEx(servo_id, position, speed, accel)
            
            # Additional delay after write for ST3215
            if self.model == "ST3215":
                time.sleep(0.02)  # 20ms delay
                
            return result, error
        except Exception as e:
            print(f"Write error: {e}")
            return COMM_FAIL, 0
            
    def read_position(self, servo_id):
        """Read position with timeout"""
        try:
            # Add delay for ST3215 before reading
            if self.model == "ST3215":
                time.sleep(0.02)  # 20ms delay
                
            pos, spd, result, error = self.packet_handler.ReadPosSpeed(servo_id)
            return pos, spd, result, error
        except Exception as e:
            print(f"Read error: {e}")
            return 0, 0, COMM_FAIL, 0
            
    def ping_servo(self, servo_id):
        """Ping servo with timeout"""
        try:
            model, result, error = self.packet_handler.ping(servo_id)
            return model, result, error
        except Exception as e:
            print(f"Ping error: {e}")
            return 0, COMM_FAIL, 0
        
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

    # Set initial active controller
    active_controller = controllers[0]
    print(f"Active controller: {active_controller.port} ({active_controller.servo_count} servos, {active_controller.model})")

    while True:
        print("\nServo Test Menu:")
        print("1. Move servo to angle")
        print("2. Center servos")
        print("3. Read positions")
        print("4. Scan for connected servos")
        print(f"c. Select controller (current: {active_controller.port}, {active_controller.model})")
        print("q. Quit")
        
        choice = input("Select option: ").strip().lower()
        
        if choice == 'q':
            break
            
        elif choice == 'c':
            print("\nAvailable controllers:")
            for i, ctrl in enumerate(controllers):
                print(f"{i+1}: {ctrl.port} ({ctrl.servo_count} servos, {ctrl.model})")
            try:
                idx = int(input("Select controller: ")) - 1
                if 0 <= idx < len(controllers):
                    active_controller = controllers[idx]
                    print(f"Selected: {active_controller.port} ({active_controller.servo_count} servos, {active_controller.model})")
                else:
                    print("Invalid selection")
            except ValueError:
                print("Invalid input")
                
        elif choice == '1':
            try:
                max_servo = active_controller.servo_count
                servo_id = int(input(f"Enter servo ID (1-{max_servo}): "))
                if not 1 <= servo_id <= max_servo:
                    print(f"Invalid servo ID. This controller has {max_servo} servo(s)")
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
                
                result, error = active_controller.write_position(servo_id, position, speed, accel)
                if result == COMM_SUCCESS:
                    print("Command sent successfully")
                    time.sleep(0.1)  # Short delay
                    # Try to read back position
                    pos, spd, result, error = active_controller.read_position(servo_id)
                    if result == COMM_SUCCESS:
                        actual_degrees = units_to_degrees(pos)
                        print(f"Current position: {actual_degrees:.1f}°")
                else:
                    print(f"Failed to move servo: {active_controller.packet_handler.getTxRxResult(result)}")
                    
            except ValueError:
                print("Invalid input")
                
        elif choice == '2':
            print(f"Centering servos on {active_controller.port}...")
            max_servo = active_controller.servo_count
            for id in range(1, max_servo + 1):
                result, error = active_controller.write_position(id, 1500, default_speed, default_accel)
                if result == COMM_SUCCESS:
                    print(f"Centered servo {id}")
                    if servo_config.get('save_positions', True):
                        save_position(config, id, 0.0)
                else:
                    print(f"Failed to center servo {id}")
                time.sleep(0.1)
                
        elif choice == '3':
            print(f"\nReading positions on {active_controller.port}:")
            max_servo = active_controller.servo_count
            for id in range(1, max_servo + 1):
                pos, spd, result, error = active_controller.read_position(id)
                if result == COMM_SUCCESS:
                    degrees = units_to_degrees(pos)
                    print(f"Servo {id}: {degrees:.1f}° (units: {pos})")
                    if servo_config.get('save_positions', True):
                        save_position(config, id, degrees)
                else:
                    print(f"Failed to read servo {id}")
                    
        elif choice == '4':
            print(f"\nScanning for servos on {active_controller.port}...")
            max_servo = active_controller.servo_count
            for id in range(1, max_servo + 1):
                model, result, error = active_controller.ping_servo(id)
                if result == COMM_SUCCESS:
                    print(f"Found servo {id}")
                    pos, spd, result, error = active_controller.read_position(id)
                    if result == COMM_SUCCESS:
                        degrees = units_to_degrees(pos)
                        print(f"  Position: {degrees:.1f}°")
                        print(f"  Speed: {spd}")
                    else:
                        print("  Could not read position")
                else:
                    print(f"No response from servo {id}")

    # Close all controllers
    for controller in controllers:
        controller.close()

if __name__ == "__main__":
    test_servos() 