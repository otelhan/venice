import asyncio
import pytest
from src.networking.reservoir_builder import ReservoirModelBuilder

async def test_reservoir_builder():
    """Test the reservoir builder functionality"""
    builder = ReservoirModelBuilder()
    
    # Verify builder initialized with config
    assert builder.config is not None
    assert builder.destination is not None
    print(f"\nBuilder initialized with destination: {builder.destination}")
    
    # Test listing available data
    files = builder.list_available_data()
    assert isinstance(files, list)
    print(f"\nFound {len(files)} data files")
    
    if files:
        # Test processing first file
        print(f"\nTesting file processing with {files[0]}")
        
        # Set the current file before starting
        builder.current_file = files[0]
        builder.current_row_index = 0  # Start with first row
        
        # Start builder in background task
        builder_task = asyncio.create_task(builder.start())
        
        try:
            # Wait for builder to process all data
            while True:
                if not builder_task.done():
                    await asyncio.sleep(1)  # Check every second
                else:
                    break
                    
                # Optional: add timeout
                # if timeout > max_timeout:
                #     raise TimeoutError("Builder took too long")
                
        except Exception as e:
            print(f"\nError during test: {e}")
        finally:
            # Clean up
            if not builder_task.done():
                builder_task.cancel()
                try:
                    await builder_task
                except asyncio.CancelledError:
                    pass
    else:
        print("\nNo data files found to test")

def main():
    """Run the tests"""
    print("\nTesting Reservoir Builder...")
    asyncio.run(test_reservoir_builder())
    print("\nTests completed")

if __name__ == "__main__":
    main() 