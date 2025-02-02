import asyncio
from src.networking.input_node import InputNode

async def run_input_node(input_node):
    """Run the input node with menu interface"""
    await input_node.discover_controllers()
    
    while True:
        print("\n=== Input Node Menu ===")
        print("1. Collect movement data")
        print("2. Send command to controller")
        print("3. Send movement data to controller")
        print("4. Get controller status")
        print("5. Exit")
        
        try:
            choice = input("\nEnter choice: ").strip()
            
            if choice == '1':
                await input_node.collect_movements()
                
            elif choice == '2':
                print("\nAvailable controllers:")
                for mac, ip in input_node.controllers.items():
                    controller_name = input_node.get_controller_name(mac)
                    print(f"{controller_name}: {mac}")
                    
                print("\nEnter controller name (e.g., 'res01') or 'q' to cancel:")
                controller = input().strip()
                if controller == 'q':
                    continue
                    
                mac = input_node.get_controller_mac(controller)
                if not mac:
                    print(f"Unknown controller: {controller}")
                    continue
                
                print("\nEnter 'd' for drive wavemaker, 'q' to quit: ")
                command = input().strip().lower()
                if command in ['d', 'q']:
                    await input_node.send_command(mac, command)
                    
            elif choice == '3':
                print("\nAvailable controllers:")
                for mac, ip in input_node.controllers.items():
                    controller_name = input_node.get_controller_name(mac)
                    print(f"{controller_name}: {mac}")
                    
                print("\nEnter controller name (e.g., 'res01') or 'q' to cancel:")
                controller = input().strip()
                if controller == 'q':
                    continue
                    
                mac = input_node.get_controller_mac(controller)
                if not mac:
                    print(f"Unknown controller: {controller}")
                    continue
                    
                await input_node.send_movement_data(mac)
                
            elif choice == '4':
                print("\nAvailable controllers:")
                for mac, ip in input_node.controllers.items():
                    controller_name = input_node.get_controller_name(mac)
                    print(f"{controller_name}: {mac}")
                    
                print("\nEnter controller name (e.g., 'res01') or 'q' to cancel:")
                controller = input().strip()
                if controller == 'q':
                    continue
                    
                mac = input_node.get_controller_mac(controller)
                if not mac:
                    print(f"Unknown controller: {controller}")
                    continue
                    
                status = await input_node.get_controller_status(mac)
                print(f"\nController status: {status}")
                
            elif choice == '5':
                print("\nExiting...")
                break
                
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    asyncio.run(run_input_node(InputNode())) 