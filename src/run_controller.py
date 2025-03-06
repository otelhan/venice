import asyncio
from src.networking.controller_node import ControllerNode
import argparse

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('name', help='Controller name (e.g., res00)')
    args = parser.parse_args()

    # Create and start controller
    try:
        controller = ControllerNode(controller_name=args.name, port=8765)
        await controller.start()
    except KeyboardInterrupt:
        print("\nController stopped")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 