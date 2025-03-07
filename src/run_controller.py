import asyncio
from src.networking.controller_node import ControllerNode
import argparse
import signal
import sys
import cv2
import matplotlib.pyplot as plt

async def main():
    # Get controller name from command line
    parser = argparse.ArgumentParser()
    parser.add_argument('controller_name', help='Name of this controller (e.g., res00)')
    args = parser.parse_args()
    
    # Print startup info
    print(f"\nStarting controller: {args.controller_name}")
    
    # Create and start controller node
    node = ControllerNode(args.controller_name)
    
    # Print config details
    print("\nController Details:")
    print(f"Name: {args.controller_name}")
    print(f"Destination: {node.controller_config.get('destination', 'None')}")
    print(f"Config: {node.controller_config}")
    
    try:
        await node.start()
    except KeyboardInterrupt:
        print("\nController stopped by user")

if __name__ == "__main__":
    print("\nController started. Press 'q' or Ctrl+C to quit")
    asyncio.run(main()) 