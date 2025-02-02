import asyncio
import signal
from src.networking.controller_node import ControllerNode

async def main():
    print("\nStarting Controller Node")
    print("----------------------")
    controller = ControllerNode()
    
    def signal_handler():
        print("\nShutdown signal received")
        asyncio.create_task(controller.stop())
    
    # Register signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_event_loop().add_signal_handler(
            sig,
            signal_handler
        )
    
    try:
        await controller.start()
    except KeyboardInterrupt:
        print("\nController shutdown requested")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("Cleaning up...")
        await controller.stop()

if __name__ == "__main__":
    asyncio.run(main()) 