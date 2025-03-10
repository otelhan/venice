import serial
import time
from typing import Dict, List, Optional

class ServoController:
    """Controls servos via Waveshare Serial Bus Servo Driver Board"""
    
    def __init__(self, port: str = '/dev/ttyACM0', baud: int = 115200):
        """Initialize servo controller
        
        Args:
            port: Serial port for the servo driver board
            baud: Baud rate for serial communication
        """
        self.port = port
        self.baud = baud
        self.serial = None
        self.connected = False
        self.servo_positions: Dict[int, int] = {}  # Track servo positions
        
    def connect(self) -> bool:
        """Connect to the servo driver board"""
        # List available ports on Linux
        print("\nAvailable Serial Ports:")
        print("----------------------")
        try:
            import glob
            ports = glob.glob('/dev/tty[A-Za-z]*')
            for port in ports:
                print(f"Port: {port}")
        except Exception as e:
            print(f"Error listing ports: {e}")
        print("----------------------")
        
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=1
            )
            self.connected = True
            print(f"Connected to servo board on {self.port}")
            return True
        except Exception as e:
            print(f"Failed to connect to servo board: {e}")
            # Try other common ports
            common_ports = ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyACM0', '/dev/ttyACM1']
            for port in common_ports:
                if port != self.port:  # Don't try the same port twice
                    try:
                        self.serial = serial.Serial(port, self.baud, timeout=1)
                        self.connected = True
                        self.port = port  # Update to working port
                        print(f"Connected to servo board on {port}")
                        return True
                    except:
                        print(f"Could not connect to {port}")
            return False
            
    def disconnect(self):
        """Disconnect from the servo driver board"""
        if self.serial:
            self.serial.close()
            self.connected = False
            
    def set_servo_position(self, servo_id: int, position: int, time_ms: int = 1000) -> bool:
        """Set servo position
        
        Args:
            servo_id: ID of the servo (1-8)
            position: Position (500-2500)
            time_ms: Time to reach position in ms
            
        Returns:
            bool: True if successful
        """
        if not self.connected:
            print("Error: Not connected to servo board")
            return False
            
        if not (1 <= servo_id <= 8):
            print("Error: Servo ID must be between 1 and 8")
            return False
            
        if not (500 <= position <= 2500):
            print("Error: Position must be between 500 and 2500")
            return False
            
        try:
            # Format command for Waveshare board
            # #<servo_id>P<position>T<time>\r\n
            cmd = f"#{servo_id}P{position}T{time_ms}\r\n"
            self.serial.write(cmd.encode())
            self.servo_positions[servo_id] = position
            return True
        except Exception as e:
            print(f"Error setting servo position: {e}")
            return False
            
    def get_servo_position(self, servo_id: int) -> Optional[int]:
        """Get last known position of a servo"""
        return self.servo_positions.get(servo_id)
        
    def center_servo(self, servo_id: int) -> bool:
        """Center a servo (position 1500)"""
        return self.set_servo_position(servo_id, 1500)
        
    def center_all_servos(self):
        """Center all servos"""
        for servo_id in range(1, 9):
            self.center_servo(servo_id)
            time.sleep(0.1)  # Small delay between servos

class OutputNode:
    """Node for controlling output devices (servos)"""
    
    def __init__(self):
        self.servo_controller = ServoController(port='/dev/ttyACM0')  # Explicitly set to ttyACM0
        
    def start(self):
        """Start the output node"""
        return self.servo_controller.connect()
        
    def stop(self):
        """Stop the output node"""
        self.servo_controller.disconnect()
        
    def handle_command(self, command):
        """Handle incoming commands"""
        if command['type'] == 'servo':
            success = self.servo_controller.set_servo_position(
                command['servo_id'],
                command['position'],
                command.get('time_ms', 1000)
            )
            if success:
                return {"status": "ok", "message": "Position set"}
            else:
                return {"status": "error", "message": "Failed to set position"}
        return {"status": "error", "message": "Unknown command type"}
