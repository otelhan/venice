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
    
    def __init__(self, port: str = '/dev/ttyACM0', baud: int = 1000000, controller_name: str = 'main'):
        """Initialize servo controller"""
        self.port = port
        self.baud = baud
        self.controller_name = controller_name  # Add this to know which controller we are
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
        self.debug = self.servo_config.get('debug', False) or \
                    self.servo_config['controllers'][controller_name].get('debug', False)
        
    def load_config(self) -> dict:
        """Load servo configuration"""
        config_path = os.path.join(self.project_root, 'config', 'controllers.yaml')
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
            
    def save_position(self, servo_id: int, angle: float):
        """Save servo position in degrees to config file"""
        # Update to use new config structure with controllers
        self.config['servo_config']['controllers'][self.controller_name]['servos'][str(servo_id)]['last_position_deg'] = angle
        
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
            
    def debug_print(self, message: str):
        """Print debug messages if debug is enabled"""
        if self.debug:
            print(f"DEBUG [{self.controller_name}]: {message}")

    def set_servo_position(self, servo_id: int, angle: float, time_ms: Optional[int] = None) -> bool:
        """Set servo position in degrees"""
        self.debug_print(f"Setting servo {servo_id} to {angle}° on {self.port}")
        
        if not self.connected:
            print("Not connected to servo board")
            return False
            
        try:
            servo_config = self.servo_config['controllers'][self.controller_name]['servos'][str(servo_id)]
            self.debug_print(f"Got servo config: {servo_config}")
            
            # Check mode
            if servo_config['mode'] != 'servo':
                print(f"Servo {servo_id} is in motor mode!")
                return False
                
            # Convert to units
            position = self.degrees_to_units(angle)
            speed = time_ms if time_ms is not None else self.default_speed
            self.debug_print(f"Converted {angle}° to {position} units, speed: {speed}ms")
            
            # Send command
            result, error = self.packet_handler.WritePosEx(servo_id, position, speed, self.default_accel)
            self.debug_print(f"WritePosEx result: {result}, error: {error}")
            
            if result == COMM_SUCCESS:
                time.sleep(0.1)
                pos, spd, result, error = self.packet_handler.ReadPosSpeed(servo_id)
                if result == COMM_SUCCESS:
                    actual_degrees = self.units_to_degrees(pos)
                    self.debug_print(f"Read position: {pos} units ({actual_degrees:.1f}°)")
                    self.save_position(servo_id, actual_degrees)
                    self.debug_print("Position saved")
                return True
            else:
                print(f"Command failed: {result}")
                return False
                
        except Exception as e:
            print(f"Error: {e}")
            return False
            
    def close(self):
        """Close the connection"""
        if self.connected:
            self.port_handler.closePort()
            self.connected = False

class OutputNode:
    """Node for controlling output devices (servos)"""
    
    def __init__(self):
        self.controllers = {}
        self.config = self.load_config()
        self.debug = self.config['servo_config'].get('debug', False)
        
        # Initialize main controller
        main_config = self.config['servo_config']['controllers']['main']
        self.controllers['main'] = ServoController(
            main_config['port'], 
            main_config['baud'],
            'main'  # Pass controller name
        )
        
        # Initialize secondary controller
        secondary_config = self.config['servo_config']['controllers']['secondary']
        self.controllers['secondary'] = ServoController(
            secondary_config['port'], 
            secondary_config['baud'],
            'secondary'  # Pass controller name
        )
        
    def load_config(self) -> dict:
        """Load servo configuration"""
        config_path = os.path.join(Path(__file__).parent.parent.parent, 'config', 'controllers.yaml')
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
            
    def start(self):
        """Start all controllers"""
        success = True
        for name, controller in self.controllers.items():
            if not controller.connect():
                print(f"Failed to connect to {name} controller")
                success = False
        return success
        
    def debug_print(self, message: str):
        """Print debug messages if debug is enabled"""
        if self.debug:
            print(f"DEBUG [OutputNode]: {message}")
            
    def process_command(self, command):
        """Process a command dictionary"""
        if command['type'] == 'servo':
            self.debug_print(f"Processing servo command: {command}")
            controller = self.controllers[command['controller']]
            result = self.move_servo(controller, command)
            self.debug_print(f"Command result: {result}")
            return result
        return {"status": "error", "message": "Unknown command type"}

    def move_servo(self, controller, command):
        """Move a servo to the specified position"""
        try:
            # Convert position to angle if it's in units
            position = command['position']
            if 500 <= position <= 2500:  # If position is in units
                position = controller.units_to_degrees(position)
                
            success = controller.set_servo_position(
                command['servo_id'],
                position,
                command.get('time_ms', None)
            )
            
            if success:
                return {"status": "ok", "message": "Position set"}
            else:
                return {"status": "error", "message": "Failed to set position"}
                
        except Exception as e:
            return {"status": "error", "message": str(e)}
