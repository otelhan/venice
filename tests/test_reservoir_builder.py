import asyncio
import sys
from pathlib import Path
import os

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.networking.reservoir_builder import ReservoirModelBuilder

async def test_reservoir_builder():
    """Test the reservoir builder functionality"""
    builder = ReservoirModelBuilder()
    
    print("\nReservoir Model Builder Test")
    print("===========================")
    
    # First test: List available data files
    print("\nTesting data file listing...")
    files = builder.list_available_data()
    if not files:
        print("No data files found in data directory!")
        return
        
    # Second test: Select and connect to reservoir
    print("\nTesting reservoir selection...")
    print("Available reservoirs:")
    reservoir = builder.select_reservoir()
    if reservoir:
        connected = await builder.connect_to_reservoir(reservoir)
        if not connected:
            print("Failed to connect to reservoir!")
            return
            
        print(f"\nSuccessfully connected to {reservoir}")
        
        # Third test: Process a data file
        print("\nTesting data processing...")
        print("Available data files:")
        files = builder.list_available_data()
        
        if files:
            try:
                print("\nSelect a file to process (or 0 to skip):")
                file_num = int(input("File number: "))
                if 1 <= file_num <= len(files):
                    print(f"\nProcessing {files[file_num-1].name}")
                    print("(Will send one row every 10 seconds)")
                    print("Press Ctrl+C to stop processing")
                    
                    try:
                        await builder.process_data_file(files[file_num-1])
                    except KeyboardInterrupt:
                        print("\nProcessing stopped by user")
                        
            except ValueError:
                print("Invalid selection")
                
        # Fourth test: Listen for output
        try:
            print("\nStarting output listener...")
            print("Press Ctrl+C to stop listening")
            builder.is_listening = True
            await builder.listen_for_data()
            
        except KeyboardInterrupt:
            print("\nListener stopped by user")
            builder.is_listening = False

def main():
    try:
        asyncio.run(test_reservoir_builder())
    except KeyboardInterrupt:
        print("\nTest stopped by user")
    finally:
        print("\nTest complete")

if __name__ == "__main__":
    main() 