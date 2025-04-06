#!/bin/bash

# Source the virtual environment
source venv/bin/activate

# Change to the project root directory
cd "$(dirname "$0")/.."

# Log start time
echo "Starting video input at $(date)"

# Run the test video input script in fullscreen mode without debug output
python -m tests.test_video_input_extended --fullscreen

# If the application exits, log the exit
echo "Video input exited at $(date)"