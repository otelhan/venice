import serial
import time
from typing import Dict, List, Optional
import yaml
import os
from pathlib import Path

from lib.STservo_sdk.sts import *
from lib.STservo_sdk.port_handler import PortHandler

class ServoController:
    """Controls servos via Waveshare Serial Bus Servo Driver Board"""
    
    def __init__(self, port: str = '/dev/ttyACM0', baud: int = 1000000):
        """Initialize servo controller"""
        self.port = port
        self.baud = baud
        self.connected = False
        self.serial = None
        self.port_handler = None
        self.packet_handler = None
        
        # Load config
        self.project_root = Path(__file__).parent.parent.parent
        self.config = self.load_config()
        self.servo_config = self.config['servo_config']
        self.default_speed = self.servo_config.get('default_speed_ms', 1000)
        self.default_accel = self.servo_config.get('default_accel', 50)
        
    def load_config(self) -> dict:
        """Load servo configuration"""
        config_path = os.path.join(self.project_root, 'config', 'controllers.yaml')
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
            
    def save_position(self, servo_id: int, angle: float):
        """Save servo position in degrees to config file"""
        self.config['servo_config']['servos'][str(servo_id)]['last_position_deg'] = angle
        
        config_path = os.path.join(self.project_root, 'config', 'controllers.yaml')
        with open(config_path, 'w') as f:
            yaml.dump(self.config, f, default_flow_style=False)
            
    def degrees_to_units(self, degrees: float) -> int:
        """Convert degrees to servo units (500-2500)"""
        # 1500 is center (0 degrees)
        # Each unit = 0.12 degrees for servo mode
        units = int(1500 + (degrees * (1000/150)))
        return max(500, min(2500, units))
        
    def units_to_degrees(self, units: int) -> float:
        """Convert servo units to degrees"""
        return (units - 1500) * 0.12
        
    def connect(self) -> bool:
        """Connect to the servo board"""
        try:
            self.port_handler = PortHandler(self.port)
            self.packet_handler = sts(self.port_handler)
            
            if not self.port_handler.openPort():
                print(f"Failed to open port {self.port}")
                return False
                
            if not self.port_handler.setBaudRate(self.baud):
                print(f"Failed to set baud rate {self.baud}")
                return False
                
            self.connected = True
            print(f"Connected to servo board on {self.port}")
            return True
            
        except Exception as e:
            print(f"Failed to connect to servo board: {e}")
            return False
            
    def set_servo_position(self, servo_id: int, angle: float, time_ms: Optional[int] = None) -> bool:
        """Set servo position in degrees"""
        if not self.connected:
            print("Not connected to servo board")
            return False
            
        try:
            # Get servo config
            servo_config = self.servo_config['servos'][str(servo_id)]
            
            # Check mode
            if servo_config['mode'] != 'servo':
                print(f"Servo {servo_id} is in motor mode!")
                return False
                
            # Validate angle
            min_angle = servo_config.get('min_angle', -150)
            max_angle = servo_config.get('max_angle', 150)
            if not min_angle <= angle <= max_angle:
                print(f"Angle {angle} out of range ({min_angle} to {max_angle})")
                return False
                
            # Convert to units
            position = self.degrees_to_units(angle)
            speed = time_ms if time_ms is not None else self.default_speed
            
            # Send command
            result, error = self.packet_handler.WritePosEx(servo_id, position, speed, self.default_accel)
            if result == COMM_SUCCESS:
                # Read back position
                time.sleep(0.1)
                pos, spd, result, error = self.packet_handler.ReadPosSpeed(servo_id)
                if result == COMM_SUCCESS:
                    actual_degrees = self.units_to_degrees(pos)
                    print(f"Servo {servo_id} moved to {actual_degrees:.1f}°")
                    self.save_position(servo_id, actual_degrees)
                return True
            else:
                print(f"Failed to move servo {servo_id}")
                return False
                
        except Exception as e:
            print(f"Error setting servo position: {e}")
            return False
            
    def close(self):
        """Close the connection"""
        if self.connected:
            self.port_handler.closePort()
            self.connected = False

class OutputNode:
    """Node for controlling output devices (servos)"""
    
    def __init__(self):
        self.servo_controller = ServoController()
        
    def start(self):
        """Start the output node"""
        return self.servo_controller.connect()
        
    def stop(self):
        """Stop the output node"""
        self.servo_controller.close()
        
    def process_command(self, command: Dict) -> Dict:
        """Process a command dictionary"""
        if command['type'] == 'servo':
            # Convert position to angle if it's in units
            position = command['position']
            if 500 <= position <= 2500:  # If position is in units
                position = self.servo_controller.units_to_degrees(position)
                
            success = self.servo_controller.set_servo_position(
                command['servo_id'],
                position,
                command.get('time_ms', None)
            )
            if success:
                return {"status": "ok", "message": "Position set"}
            else:
                return {"status": "error", "message": "Failed to set position"}
        return {"status": "error", "message": "Unknown command type"}
