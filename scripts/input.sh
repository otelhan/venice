#!/bin/bash

# Input node launcher script

# Default values
MODE="operation"
VERBOSE=0  # Default to minimal logging
EXTRA_ARGS=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --test)
      MODE="test"
      shift
      ;;
    --operation)
      MODE="operation"
      shift
      ;;
    --verbose)
      VERBOSE=1  # Normal logging
      shift
      ;;
    --debug)
      VERBOSE=2  # Debug logging
      shift
      ;;
    *)
      EXTRA_ARGS="$EXTRA_ARGS $1"
      shift
      ;;
  esac
done

# Navigate to the project directory
cd "$(dirname "$0")/.."
echo "Working directory: $(pwd)"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Run the input node
echo "Starting video input in $MODE mode, verbosity: $VERBOSE"
python -m tests.test_video_input_extended --verbose $VERBOSE $EXTRA_ARGS 