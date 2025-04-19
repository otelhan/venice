#!/bin/bash

# Change to the project root directory
cd "$(dirname "$0")/.."

# Source the virtual environment
source venv/bin/activate

# Parse command line arguments
USE_VIDEO=false
USE_STREAM=false
USE_RANDOM=false
USE_SEQUENCE=false
FULLSCREEN=false
SCREEN_MODE=false

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
        --sequence)
            USE_SEQUENCE=true
            shift
            ;;
        --fullscreen)
            FULLSCREEN=true
            shift
            ;;
        --screen)
            SCREEN_MODE=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--video] [--stream] [--random] [--sequence] [--fullscreen] [--screen]"
            exit 1
            ;;
    esac
done

# Build the command based on arguments
CMD="python -m tests.test_video_input_extended"

if [ "$FULLSCREEN" = true ]; then
    CMD="$CMD --fullscreen"
fi

if [ "$SCREEN_MODE" = true ]; then
    CMD="$CMD --screen"
fi

# Handle the video source options - make sure only one is specified
if [ "$USE_VIDEO" = true ] && [ "$USE_STREAM" = true ]; then
    echo "Error: Cannot specify both --video and --stream"
    echo "Usage: $0 [--video] [--stream] [--random] [--sequence] [--fullscreen] [--screen]"
    exit 1
fi

if [ "$USE_VIDEO" = true ] && [ "$USE_RANDOM" = true ]; then
    echo "Error: Cannot specify both --video and --random"
    echo "Usage: $0 [--video] [--stream] [--random] [--sequence] [--fullscreen] [--screen]"
    exit 1
fi

if [ "$USE_VIDEO" = true ] && [ "$USE_SEQUENCE" = true ]; then
    echo "Error: Cannot specify both --video and --sequence"
    echo "Usage: $0 [--video] [--stream] [--random] [--sequence] [--fullscreen] [--screen]"
    exit 1
fi

if [ "$USE_STREAM" = true ] && [ "$USE_RANDOM" = true ]; then
    echo "Error: Cannot specify both --stream and --random"
    echo "Usage: $0 [--video] [--stream] [--random] [--sequence] [--fullscreen] [--screen]"
    exit 1
fi

if [ "$USE_STREAM" = true ] && [ "$USE_SEQUENCE" = true ]; then
    echo "Error: Cannot specify both --stream and --sequence"
    echo "Usage: $0 [--video] [--stream] [--random] [--sequence] [--fullscreen] [--screen]"
    exit 1
fi

if [ "$USE_RANDOM" = true ] && [ "$USE_SEQUENCE" = true ]; then
    echo "Error: Cannot specify both --random and --sequence"
    echo "Usage: $0 [--video] [--stream] [--random] [--sequence] [--fullscreen] [--screen]"
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
else
    echo "Error: Must specify one of --video, --stream, --random, or --sequence"
    echo "Usage: $0 [--video] [--stream] [--random] [--sequence] [--fullscreen] [--screen]"
    exit 1
fi

echo "Executing: $CMD"

# Run the command
eval $CMD