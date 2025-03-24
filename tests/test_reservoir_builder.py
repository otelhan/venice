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
        await builder.process_data_file(files[0])
    else:
        print("\nNo data files found to test")

def main():
    """Run the tests"""
    print("\nTesting Reservoir Builder...")
    asyncio.run(test_reservoir_builder())
    print("\nTests completed")

if __name__ == "__main__":
    main() 