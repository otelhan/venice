import asyncio
import argparse
from src.networking.controller_node import ControllerNode
import signal
import sys
import cv2
import matplotlib.pyplot as plt

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('controller_name', help='Name of the controller (e.g., res00)')
    args = parser.parse_args()
    
    print(f"\nStarting controller: {args.controller_name}")
    
    # Create and start controller node
    node = ControllerNode(args.controller_name)
    await node.start()

if __name__ == "__main__":
    print("\nController started. Press 'q' or Ctrl+C to quit")
    asyncio.run(main()) 