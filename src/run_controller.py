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
    try:
        print(f"\nStarting controller {args.name}...")
        print("Waiting for commands/data...")
        await controller.start()
    except KeyboardInterrupt:
        print("\nShutdown requested")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await controller.stop()

if __name__ == "__main__":
    asyncio.run(main()) 