import asyncio
from src.networking.controller_node import ControllerNode
import argparse
import signal
import sys
import cv2
import matplotlib.pyplot as plt

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('name', help='Controller name (e.g., res00)')
    args = parser.parse_args()

    # Create and start controller
    try:
        controller = ControllerNode(controller_name=args.name, port=8765)
        
        # Handle Ctrl+C and 'q' gracefully
        def signal_handler(sig, frame):
            print("\nShutting down controller...")
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        
        # Start keyboard input monitoring
        async def check_input():
            while True:
                try:
                    cmd = await asyncio.get_event_loop().run_in_executor(None, input)
                    if cmd.lower() == 'q':
                        print("\nShutting down controller...")
                        # Cleanup before exit
                        if hasattr(controller, 'state_handler'):
                            if hasattr(controller.state_handler, 'camera'):
                                controller.state_handler.camera.stop_camera()
                        cv2.destroyAllWindows()
                        plt.close('all')
                        sys.exit(0)
                except Exception as e:
                    print(f"Error in input handling: {e}")
                await asyncio.sleep(0.1)
        
        # Run both the controller and input checking
        await asyncio.gather(
            controller.start(),
            check_input()
        )
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("\nController started. Press 'q' or Ctrl+C to quit")
    asyncio.run(main()) 