#!/bin/bash

# Source the virtual environment
source venv/bin/activate

# Change to the project root directory
cd "$(dirname "$0")/.."

# Run the test video input script in fullscreen mode with debug output
python -m tests.test_video_input_extended --fullscreen --debug 