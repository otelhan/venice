import asyncio
from src.networking.input_node import InputNode
from src.networking.controller_node import ControllerNode

async def test_data_transmission():
    """Test data transmission between input node and controller"""
    # Start a controller node (server)
    controller = ControllerNode()
    await controller.start()
    print("Controller node started")
    
    # Create input node (client)
    input_node = InputNode()
    await input_node.discover_controllers()
    
    while True:
        print("\nTest Options:")
        print("1. Send command to controller")
        print("2. Send data packet")
        print("3. Get controller status")
        print("q. Quit")
        
        choice = input("\nEnter choice: ").lower()
        
        if choice == 'q':
            break
            
        if choice == '1':
            command = input("Enter command ('c' for collect, 'd' for drive): ")
            await input_node.send_command("00:00:00:00:00:00", command)
            
        elif choice == '2':
            # Example data packet
            data = {
                'timestamp': 123456789,
                'values': [1.2, 3.4, 5.6],
                'metadata': {
                    'type': 'test_data',
                    'source': 'input_node'
                }
            }
            await input_node.send_data("00:00:00:00:00:00", data)
            
        elif choice == '3':
            status = await input_node.get_controller_status("00:00:00:00:00:00")
            print(f"Controller status: {status}")
            
        await asyncio.sleep(0.1)  # Small delay between operations

async def main():
    print("\nController Communication Test")
    print("----------------------------")
    try:
        await test_data_transmission()
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    finally:
        # Cleanup
        print("Cleaning up...")
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in tasks]
        await asyncio.gather(*tasks, return_exceptions=True)

if __name__ == "__main__":
    asyncio.run(main()) 