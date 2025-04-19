#!/bin/bash

# Source the virtual environment
source venv/bin/activate

# Change to the project root directory
cd "$(dirname "$0")/.."

# Set up logging
LOG_FILE="$(pwd)/logs/background_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$(dirname $LOG_FILE)"
exec > "$LOG_FILE" 2>&1

echo "===== Starting Background Video Processor ====="
echo "Date: $(date)"

# Parse command line arguments - defaulting to random
USE_VIDEO=false
USE_STREAM=false
USE_RANDOM=true  # Default to random
USE_SEQUENCE=false
FULLSCREEN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --video)
            USE_VIDEO=true
            USE_RANDOM=false  # Override default
            USE_SEQUENCE=false
            shift
            ;;
        --stream)
            USE_STREAM=true
            USE_RANDOM=false  # Override default
            USE_SEQUENCE=false
            shift
            ;;
        --random)
            USE_RANDOM=true
            USE_SEQUENCE=false
            shift
            ;;
        --sequence)
            USE_SEQUENCE=true
            USE_RANDOM=false  # Override default
            shift
            ;;
        --fullscreen)
            FULLSCREEN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--video] [--stream] [--random] [--sequence] [--fullscreen]"
            exit 1
            ;;
    esac
done

# Build the command based on arguments
CMD="python -m tests.test_video_input_extended"

if [ "$FULLSCREEN" = true ]; then
    CMD="$CMD --fullscreen"
fi

# Handle the video source options - make sure only one is specified
if [ "$USE_VIDEO" = true ] && [ "$USE_STREAM" = true ]; then
    echo "Error: Cannot specify both --video and --stream"
    exit 1
fi

if [ "$USE_VIDEO" = true ] && [ "$USE_RANDOM" = true ]; then
    echo "Error: Cannot specify both --video and --random"
    exit 1
fi

if [ "$USE_STREAM" = true ] && [ "$USE_RANDOM" = true ]; then
    echo "Error: Cannot specify both --stream and --random"
    exit 1
fi

if [ "$USE_VIDEO" = true ] && [ "$USE_SEQUENCE" = true ]; then
    echo "Error: Cannot specify both --video and --sequence"
    exit 1
fi

if [ "$USE_STREAM" = true ] && [ "$USE_SEQUENCE" = true ]; then
    echo "Error: Cannot specify both --stream and --sequence"
    exit 1
fi

if [ "$USE_RANDOM" = true ] && [ "$USE_SEQUENCE" = true ]; then
    echo "Error: Cannot specify both --random and --sequence"
    exit 1
fi

# Add the appropriate video source flag
if [ "$USE_VIDEO" = true ]; then
    CMD="$CMD --video"
elif [ "$USE_STREAM" = true ]; then
    CMD="$CMD --stream"
elif [ "$USE_RANDOM" = true ]; then
    CMD="$CMD --random"
elif [ "$USE_SEQUENCE" = true ]; then
    CMD="$CMD --sequence"
fi

# Support running in a non-interactive environment
# by creating a virtual display if needed
if [ -z "$DISPLAY" ]; then
    echo "No display detected, running with virtual display"
    
    # Check if xvfb is installed
    if command -v xvfb-run &> /dev/null; then
        CMD="xvfb-run -a $CMD"
    else
        echo "Warning: xvfb-run not found. GUI windows may fail."
        # Still try to run with null display
        export DISPLAY=:0
    fi
fi

echo "Executing: $CMD"

# Run the command
eval $CMD
EXIT_CODE=$?

echo "Process exited with code: $EXIT_CODE"
echo "===== Background Video Processor Ended ====="
echo "End time: $(date)"