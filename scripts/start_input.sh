#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Get the repository root directory (one level up from scripts)
REPO_DIR="$( cd "$SCRIPT_DIR/.." &> /dev/null && pwd )"

# Navigate to the repository directory
cd "$REPO_DIR"

# Activate the virtual environment
source venv/bin/activate

# Run the video input test
python -m tests.test_video_input 