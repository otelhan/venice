import asyncio
from src.networking.controller_node import ControllerNode
import argparse

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('name', help='Controller name (e.g., res01)')
    args = parser.parse_args()

    # Initialize controller with name
    controller = ControllerNode(name=args.name, port=8765)
    await controller.start()

if __name__ == "__main__":
    asyncio.run(main())