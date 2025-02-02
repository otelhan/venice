import asyncio
from src.networking.input_node import InputNode

async def main():
    print("\nStarting Input Node")
    print("-----------------")
    input_node = InputNode()
    await input_node.discover_controllers()
    
    commands = {
        'd': 'Drive wavemaker',
        'c': 'Collect signal',
        'i': 'Idle',
        'p': 'Process data',
        's': 'Send collected data',
        'r': 'Receive data'
    }
    
    while True:
        print("\nOptions:")
        print("1. Collect movement data")
        print("2. Send command to controller")
        print("3. Send collected data")
        print("4. Get controller status")
        print("q. Quit")
        
        choice = input("\nEnter choice: ").lower()
        
        if choice == 'q':
            break
            
        if choice == '1':
            # Collect new movement data
            await input_node.collect_movements()
            
        elif choice == '2':
            print("\nAvailable commands:")
            for cmd, desc in commands.items():
                print(f"{cmd}: {desc}")
            command = input("Enter command: ").lower()
            if command in commands:
                await input_node.send_command("00:00:00:00:00:00", command)
            else:
                print("Invalid command")
                
        elif choice == '3':
            # Send collected movement data
            if input_node.movement_buffer:
                print(f"Sending {len(input_node.movement_buffer)} measurements...")
                await input_node.send_movement_data("00:00:00:00:00:00")
            else:
                print("No data collected yet! Use option 1 first.")
                
        elif choice == '4':
            status = await input_node.get_controller_status("00:00:00:00:00:00")
            print(f"Controller status: {status}")

if __name__ == "__main__":
    asyncio.run(main()) 