#!/bin/bash

# Source the virtual environment
source venv/bin/activate

# Change to the project root directory
cd "$(dirname "$0")/.."

# Parse command line arguments
USE_VIDEO=false
USE_STREAM=false
FULLSCREEN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --video)
            USE_VIDEO=true
            shift
            ;;
        --stream)
            USE_STREAM=true
            shift
            ;;
        --fullscreen)
            FULLSCREEN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--video] [--stream] [--fullscreen]"
            exit 1
            ;;
    esac
done

# Build the command based on arguments
CMD="python -m tests.test_video_input_extended"

if [ "$FULLSCREEN" = true ]; then
    CMD="$CMD --fullscreen"
fi

if [ "$USE_VIDEO" = true ]; then
    CMD="$CMD --video"
elif [ "$USE_STREAM" = true ]; then
    CMD="$CMD --stream"
else
    echo "Error: Either --video or --stream must be specified"
    echo "Usage: $0 [--video] [--stream] [--fullscreen]"
    exit 1
fi

# Run the command
eval $CMD