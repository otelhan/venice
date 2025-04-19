#!/bin/bash

# Script name: headless_output.sh
# Purpose: Headless version of output.sh for running output processing as a service

# Change to the project root directory
cd "$(dirname "$0")/.."

# Source the virtual environment
source venv/bin/activate

# Create log directory and file
LOG_DIR="$(pwd)/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/headless_output_$(date +%Y%m%d_%H%M%S).log"
exec > "$LOG_FILE" 2>&1

echo "===== Starting Headless Output Processor ====="
echo "Date: $(date)"
echo "Working directory: $(pwd)"

# Parse command line arguments
# Add your specific arguments here, similar to the original output.sh
# For example:
OUTPUT_TYPE=""
ADDITIONAL_OPTIONS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --type)
            OUTPUT_TYPE="$2"
            shift 2
            ;;
        --option)
            ADDITIONAL_OPTIONS="$ADDITIONAL_OPTIONS --$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--type TYPE] [--option OPTION]"
            exit 1
            ;;
    esac
done

# Set default output type if not specified
if [ -z "$OUTPUT_TYPE" ]; then
    OUTPUT_TYPE="default"
    echo "No output type specified, using default"
fi

# Build the command
# Replace this with the actual command from output.sh
CMD="python -m src.run_output $OUTPUT_TYPE $ADDITIONAL_OPTIONS"

# Support running in a non-interactive environment
# by creating a virtual display if needed
if [ -z "$DISPLAY" ]; then
    echo "No display detected, running with virtual display"
    
    # Check if xvfb is installed
    if command -v xvfb-run &> /dev/null; then
        CMD="xvfb-run -a $CMD"
    else
        echo "Warning: xvfb-run not found. GUI operations may fail."
        # Still try to run with null display
        export DISPLAY=:0
    fi
fi

echo "Executing: $CMD"

# Run the command
eval $CMD
EXIT_CODE=$?

echo "Process exited with code: $EXIT_CODE"
echo "===== Headless Output Processor Ended ====="
echo "End time: $(date)"