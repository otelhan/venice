import time
import glob
import sys
import os
import yaml

# Get absolute path to lib directory
lib_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lib'))
sys.path.append(lib_path)

print(f"Looking for SDK in: {lib_path}")
try:
    from STservo_sdk.port_handler import PortHandler
    from STservo_sdk.sts import *
    from STservo_sdk.stservo_def import *
    print("Successfully imported SDK")
except ImportError as e:
    print(f"Error importing STservo_sdk: {e}")
    print("Directory contents:")
    for root, dirs, files in os.walk(lib_path):
        print(f"\nDirectory: {root}")
        print("Files:", files)
        print("Subdirs:", dirs)
    sys.exit(1)

from src.networking.output_node import OutputNode, ServoController

# Add register definitions at the top with other imports
SMS_STS_ID = 0x05          # ID register address
SMS_STS_LOCK = 0x37        # Lock register (0x37 = 55 in decimal)

def find_servo_board():
    """Find the Waveshare servo board port"""
    # Try different possible ports
    ports = [
        # Linux/Raspberry Pi
        '/dev/ttyUSB0',
        '/dev/ttyUSB1',
        '/dev/ttyACM0',
        '/dev/ttyACM1',
        
        # Windows
        'COM3',
        'COM4',
        
        # Mac ports
        '/dev/tty.usbserial*',     # Most common for USB-Serial adapters
        '/dev/tty.SLAB_USBtoUART', # Silicon Labs adapter
        '/dev/tty.wchusbserial*',  # CH340 adapter
        '/dev/tty.usbmodem*'       # Native USB
    ]
    
    # List available ports
    available_ports = []
    for pattern in ports:
        available_ports.extend(glob.glob(pattern))
    
    print("\nAvailable ports:")
    for port in available_ports:
        print(f"- {port}")
    
    if not available_ports:
        print("No serial ports found!")
        print("\nTroubleshooting tips:")
        print("1. Make sure the board is connected")
        print("2. On Mac, check if driver is installed:")
        print("   - For CH340: https://www.wch.cn/downloads/CH34XSER_MAC_ZIP.html")
        print("   - For CP210x: https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers")
        print("3. On Mac, check System Preferences -> Security & Privacy if driver needs approval")
        print("4. On Linux, check if user has permission to access serial ports")
        return None
        
    # Let user choose if multiple ports found
    if len(available_ports) > 1:
        print("\nMultiple ports found. Please choose:")
        for i, port in enumerate(available_ports):
            print(f"{i+1}: {port}")
        try:
            choice = int(input("\nEnter number: ").strip()) - 1
            if 0 <= choice < len(available_ports):
                return available_ports[choice]
        except ValueError:
            print("Invalid choice")
            return None
    
    return available_ports[0] if available_ports else None

def scan_servos(node):
    """Scan for connected servos using Waveshare SDK ping"""
    print("\nScanning for connected servos...")
    connected_servos = []
    
    # Initialize port handler
    portHandler = PortHandler(node.servo_controller.port)
    
    # Open port
    if portHandler.openPort():
        print("Succeeded to open the port")
    else:
        print("Failed to open the port")
        return []
    
    # Set baudrate
    if portHandler.setBaudRate(1000000):  # 1Mbps
        print("Succeeded to change the baudrate")
    else:
        print("Failed to change the baudrate")
        portHandler.closePort()
        return []
    
    # Initialize PacketHandler
    packetHandler = sts(portHandler)
    
    try:
        # Scan IDs 1-10
        for sts_id in range(1, 11):  # Changed to scan 1-10
            print(f"\nPinging ID {sts_id}...", end='', flush=True)
            
            # Clear the port buffer before each ping
            portHandler.clearPort()
            time.sleep(0.02)  # Short delay after clear
            
            # Try to ping the servo
            sts_model_number, sts_comm_result, sts_error = packetHandler.ping(sts_id)
            
            if sts_comm_result == COMM_SUCCESS:
                print(f"\n[ID:{sts_id:03d}] Found! Model number : {sts_model_number}")
                connected_servos.append(sts_id)
                
                # Give bus time to settle
                time.sleep(0.05)
                
                # Try to read current position
                try:
                    pos_result = packetHandler.read4ByteTxRx(sts_id, STS_PRESENT_POSITION_L)
                    if pos_result[0] == COMM_SUCCESS:
                        print("Present Position : %d" % pos_result[1])
                except:
                    pass
            else:
                print(" Not found")
                
            # Delay between pings
            time.sleep(0.1)
            
    except Exception as e:
        print(f"Error during scan: {e}")
    
    finally:
        print("\nClosing port...")
        portHandler.closePort()
    
    if connected_servos:
        print(f"\nFound {len(connected_servos)} servos:")
        for servo_id in connected_servos:
            print(f"- Servo ID: {servo_id}")
        print("\nNote: Multiple servos can be controlled independently")
    else:
        print("\nNo servos found!")
        
    return connected_servos

def move_servo(port, servo_id, position, time_ms):
    """Move servo using SyncWritePosEx from example"""
    portHandler = PortHandler(port)
    if not portHandler.openPort():
        print("Failed to open port")
        return False
        
    if not portHandler.setBaudRate(1000000):
        print("Failed to set baudrate")
        portHandler.closePort()
        return False
        
    packetHandler = sts(portHandler)
    
    try:
        # Set moving speed and acceleration
        STS_MOVING_SPEED = 2400  # From example
        STS_MOVING_ACC = 50      # From example
        
        print(f"Moving servo {servo_id} to position {position}...")
        
        # Add servo position to sync write
        sts_addparam_result = packetHandler.SyncWritePosEx(servo_id, position, STS_MOVING_SPEED, STS_MOVING_ACC)
        if not sts_addparam_result:
            print("SyncWrite addparam failed")
            return False
            
        # Execute the sync write
        sts_comm_result = packetHandler.groupSyncWrite.txPacket()
        if sts_comm_result != COMM_SUCCESS:
            print("%s" % packetHandler.getTxRxResult(sts_comm_result))
            return False
            
        # Clear sync write parameter storage
        packetHandler.groupSyncWrite.clearParam()
        
        # Wait a bit for the movement to start
        time.sleep(0.002)
        
        # Wait for movement to complete
        while True:
            # Read moving status
            moving_result = packetHandler.read1ByteTxRx(servo_id, STS_MOVING)
            if moving_result[0] != COMM_SUCCESS:
                print("Failed to read moving status")
                break
                
            if moving_result[1] == 0:  # Not moving
                break
                
            time.sleep(0.1)  # Check every 100ms
            
        return True
        
    except Exception as e:
        print(f"Error moving servo: {e}")
        return False
        
    finally:
        portHandler.closePort()

def test_output_node():
    """Test Waveshare servo board control"""
    print("\nOutput Node Test")
    print("---------------")
    
    # Find servo board port
    port = find_servo_board()
    if not port:
        print("ERROR: Could not find servo board!")
        return
        
    # Create output node with found port
    node = OutputNode()
    node.servo_controller.port = port
    node.servo_controller.baudrate = 1000000  # Set correct baudrate
    
    if not node.start():
        print("Failed to start output node")
        return
    
    # Scan for connected servos using SDK ping
    connected_servos = scan_servos(node)
    if not connected_servos:
        print("No servos detected! Please check connections.")
        node.stop()
        return
        
    try:
        while True:
            print("\nCommands:")
            print("1. Scan for servos")
            print("2. Move servo")
            print("3. Center servo")
            print("4. Change servo ID")
            print("5. Setup new servo")
            print("q. Quit")
            
            cmd = input("\nEnter command: ").strip().lower()
            
            if cmd == 'q':
                break
                
            elif cmd == '1':
                print("\nScanning for servos...")
                connected_servos = scan_servos(node)
                if not connected_servos:
                    print("No servos detected! Please check connections.")
                
            elif cmd == '2':
                try:
                    print("\nAvailable servos:", connected_servos)
                    servo_id = int(input("Enter servo ID (0-255): "))
                    
                    if servo_id not in connected_servos:
                        print(f"Error: Servo {servo_id} not found! Available servos: {connected_servos}")
                        continue
                        
                    position = int(input("Enter position (500-2500): "))
                    time_ms = int(input("Enter time in ms (100-5000): "))
                    
                    if not (500 <= position <= 2500):
                        print("Error: Position must be between 500 and 2500")
                        continue
                        
                    if not (100 <= time_ms <= 5000):
                        print("Error: Time must be between 100 and 5000 ms")
                        continue
                    
                    success = move_servo(node.servo_controller.port, servo_id, position, time_ms)
                    if success:
                        print("Servo moved successfully")
                    else:
                        print("Failed to move servo")
                    
                except ValueError:
                    print("Invalid input! Please enter numbers only.")
            
            elif cmd == '3':
                try:
                    print("\nAvailable servos:", connected_servos)
                    servo_id = int(input("Enter servo ID (0-255): "))
                    
                    if servo_id not in connected_servos:
                        print(f"Error: Servo {servo_id} not found! Available servos: {connected_servos}")
                        continue
                    
                    success = move_servo(node.servo_controller.port, servo_id, 1500, 1000)  # Center position
                    if success:
                        print("Servo centered successfully")
                    else:
                        print("Failed to center servo")
                    
                except ValueError:
                    print("Invalid input! Please enter a valid servo ID.")
            
            elif cmd == '4':
                try:
                    print("\nAvailable servos:", connected_servos)
                    old_id = int(input("Enter current servo ID: "))
                    
                    if old_id not in connected_servos:
                        print(f"Error: Servo {old_id} not found!")
                        continue
                    
                    new_id = int(input("Enter new ID (0-253): "))
                    if not (0 <= new_id <= 253):
                        print("Error: ID must be between 0 and 253")
                        continue
                        
                    if new_id in connected_servos:
                        print(f"Error: ID {new_id} is already in use!")
                        continue
                    
                    if change_servo_id(node.servo_controller.port, old_id, new_id):
                        # Update connected_servos list
                        connected_servos.remove(old_id)
                        connected_servos.append(new_id)
                        connected_servos.sort()
                        
                        # Save to config
                        save_servo_config(connected_servos)
                    
                except ValueError:
                    print("Invalid input! Please enter numbers only.")
            
            elif cmd == '5':
                setup_new_servo()
            
            else:
                print("Invalid command")
                
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    finally:
        print("\nClosing connection...")
        node.stop()

def load_servo_config():
    """Load servo IDs from config file"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.yaml')
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            return config.get('servos', {}).get('ids', [])
    except Exception as e:
        print(f"Warning: Could not load servo config: {e}")
        return []

def save_servo_config(servo_ids):
    """Save servo IDs to config file"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'config.yaml')
    try:
        # Load existing config
        config = {}
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        
        # Update servo IDs
        if 'servos' not in config:
            config['servos'] = {}
        config['servos']['ids'] = sorted(servo_ids)
        
        # Save config
        with open(config_path, 'w') as f:
            yaml.safe_dump(config, f, default_flow_style=False)
        print(f"Saved servo IDs to config file: {servo_ids}")
        
    except Exception as e:
        print(f"Warning: Could not save servo config: {e}")

def setup_new_servo():
    """Setup process for a new servo"""
    print("\nNew Servo Setup Process")
    print("----------------------")
    print("IMPORTANT: Connect only ONE new servo at a time!")
    print("1. New servos always start with ID 1 (factory default)")
    print("2. We'll verify it's responding")
    print("3. Then assign it a unique ID")
    
    input("\nPress Enter when you have connected ONE new servo...")
    
    # Initialize connection
    portHandler = PortHandler(node.servo_controller.port)
    if not portHandler.openPort() or not portHandler.setBaudRate(1000000):
        print("Failed to open port")
        return
        
    packetHandler = sts(portHandler)
    
    try:
        # First verify we can talk to the servo at ID 1
        print("\nChecking for servo with factory ID (1)...")
        model_number, comm_result, error = packetHandler.ping(1)
        
        if comm_result != COMM_SUCCESS:
            print("Error: Cannot find servo with ID 1!")
            print("Make sure:")
            print("1. Only one servo is connected")
            print("2. Power is connected (USB is not enough)")
            print("3. Servo is factory fresh or known to have ID 1")
            return
            
        print(f"Success! Found servo with ID 1 (Model: {model_number})")
        
        # Read current EEPROM values
        print("\nReading current EEPROM settings:")
        try:
            current_id = packetHandler.read1ByteTxRx(1, 0x05)[1]  # ID
            baud_rate = packetHandler.read1ByteTxRx(1, 0x06)[1]   # Baud Rate
            print(f"Current ID: {current_id}")
            print(f"Baud Rate: {baud_rate}")
        except:
            print("Could not read all EEPROM values")
        
        # Get new ID from user
        while True:
            try:
                new_id = int(input("\nEnter new ID for this servo (2-253): "))
                if 2 <= new_id <= 253:
                    break
                print("ID must be between 2 and 253")
            except ValueError:
                print("Please enter a valid number")
        
        # Write new ID to EEPROM
        print(f"\nChanging servo ID from 1 to {new_id}...")
        result = packetHandler.write1ByteTxRx(1, 0x05, new_id)
        time.sleep(0.5)  # Give time for EEPROM write
        
        # Verify the change
        print("Verifying new ID...")
        model_number, comm_result, error = packetHandler.ping(new_id)
        if comm_result == COMM_SUCCESS:
            print(f"Success! Servo is now responding to ID {new_id}")
            print("\nIMPORTANT: Write down or label this servo with its new ID!")
            print("You can now disconnect this servo and connect the next one.")
        else:
            print("Error: Could not verify new ID!")
            print("The servo may need to be reset to factory settings.")
            
    finally:
        portHandler.closePort()

def change_servo_id(port, old_id, new_id):
    """Change servo ID following SMS_STS.cpp implementation"""
    if not (0 <= new_id <= 253):
        print("Error: New ID must be between 0 and 253")
        return False
        
    portHandler = PortHandler(port)
    if not portHandler.openPort() or not portHandler.setBaudRate(1000000):
        print("Failed to open port")
        return False
        
    packetHandler = sts(portHandler)
    
    try:
        # First check if servo responds
        print(f"Checking servo {old_id}...")
        model_number, comm_result, error = packetHandler.ping(old_id)
        if comm_result != COMM_SUCCESS:
            print(f"Error: Cannot find servo {old_id}")
            return False
            
        # Unlock EPROM using original ID
        print("Unlocking EPROM...")
        result, error = packetHandler.write1ByteTxRx(old_id, 0x37, 0)  # 0x37 = 55 (LOCK register)
        print(f"Unlock result: {result}, error: {error}")
        if result != COMM_SUCCESS:
            print(f"Failed to unlock EPROM: {packetHandler.getTxRxResult(result)}")
            if error != 0:
                print(f"Error detail: {packetHandler.getRxPacketError(error)}")
            return False
            
        time.sleep(0.1)  # Wait for EPROM
        
        # Write new ID
        print(f"Writing new ID {new_id} to EPROM...")
        result, error = packetHandler.write1ByteTxRx(old_id, 0x05, new_id)  # 0x05 is ID register
        print(f"Write ID result: {result}, error: {error}")
        if result != COMM_SUCCESS:
            print(f"Failed to write new ID: {packetHandler.getTxRxResult(result)}")
            if error != 0:
                print(f"Error detail: {packetHandler.getRxPacketError(error)}")
            return False
            
        time.sleep(0.5)  # Wait for EPROM write
        
        # Lock EPROM using original ID
        print("Locking EPROM...")
        result, error = packetHandler.write1ByteTxRx(old_id, 0x37, 1)  # Use old_id instead of new_id
        print(f"Lock result: {result}, error: {error}")
        if result != COMM_SUCCESS:
            print(f"Warning - Failed to lock EPROM: {packetHandler.getTxRxResult(result)}")
            if error != 0:
                print(f"Error detail: {packetHandler.getRxPacketError(error)}")
            
        # Verify change
        print("Verifying new ID...")
        model_number, comm_result, error = packetHandler.ping(new_id)
        if comm_result == COMM_SUCCESS:
            print(f"Successfully verified ID change to {new_id}")
            return True
        else:
            print("Failed to verify new ID")
            if error != 0:
                print(f"Error detail: {packetHandler.getRxPacketError(error)}")
            return False
            
    finally:
        portHandler.closePort()

if __name__ == "__main__":
    test_output_node() 