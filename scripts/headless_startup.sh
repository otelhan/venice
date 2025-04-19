#!/bin/bash

# Script name: headless_startup.sh

# Source the virtual environment
source venv/bin/activate

# Change to the project root directory
cd "$(dirname "$0")/.."

# Parse command line arguments
USE_VIDEO=false
USE_STREAM=false
USE_RANDOM=false
FULLSCREEN=false
SCREEN_MODE=true  # Always true for headless version

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
        --random)
            USE_RANDOM=true
            shift
            ;;
        --fullscreen)
            FULLSCREEN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--video] [--stream] [--random] [--fullscreen]"
            exit 1
            ;;
    esac
done

# Create log file path
LOG_FILE="$(pwd)/logs/headless_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$(dirname $LOG_FILE)"
exec > "$LOG_FILE" 2>&1

echo "===== Starting Headless Video Processor ====="
echo "Date: $(date)"

# Build the command based on arguments
CMD="python -m tests.test_video_input_extended --screen"

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

# Add the appropriate video source flag
if [ "$USE_VIDEO" = true ]; then
    CMD="$CMD --video"
elif [ "$USE_STREAM" = true ]; then
    CMD="$CMD --stream"
elif [ "$USE_RANDOM" = true ]; then
    CMD="$CMD --random"
else
    echo "Error: Must specify one of --video, --stream, or --random"
    exit 1
fi

# Set environment variables for headless operation
export MPLBACKEND=Agg
export PYTHONUNBUFFERED=1
export PYTHONPATH=.
#export OPENCV_VIDEOIO_PRIORITY_MSMF=0
#export QT_QPA_PLATFORM=offscreen

echo "Executing: $CMD"
echo "Environment: MPLBACKEND=$MPLBACKEND, QT_QPA_PLATFORM=$QT_QPA_PLATFORM"

# Run the command
eval $CMD
EXIT_CODE=$?

echo "Process exited with code: $EXIT_CODE"
echo "===== Headless Video Processor Ended ====="
echo "End time: $(date)"