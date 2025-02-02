import asyncio
from networking.controller_node import ControllerNode

async def main():
    controller = ControllerNode()
    try:
        print("Starting controller node...")
        await controller.start()
    except KeyboardInterrupt:
        print("\nShutting down controller...")

if __name__ == "__main__":
    asyncio.run(main()) 