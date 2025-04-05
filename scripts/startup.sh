#!/bin/bash

# Source the virtual environment
source venv/bin/activate

# Change to the project root directory
cd "$(dirname "$0")/.."

# Run the test video input script
python3 tests/test_video_input_extended.py