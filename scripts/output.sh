#!/bin/bash
# Script to run the output controller
# This can be used in both operation mode and test mode

# Navigate to the project root directory
cd "$(dirname "$0")/.."

# Default values
MODE="operation"
VERBOSE=0  # Default to minimal logging
PORT=8765
EXTRA_ARGS=""
NON_INTERACTIVE="--non-interactive"

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
    --port)
      PORT="$2"
      shift 2
      ;;
    --verbose)
      VERBOSE=1  # Normal logging
      shift
      ;;
    --debug)
      VERBOSE=2  # Debug logging
      shift
      ;;
    --interactive)
      NON_INTERACTIVE=""  # Remove non-interactive flag
      shift
      ;;
    *)
      EXTRA_ARGS="$EXTRA_ARGS $1"
      shift
      ;;
  esac
done

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Display startup message
echo "Starting output controller in $MODE mode"
echo "Port: $PORT"
echo "Verbosity: $VERBOSE"
if [ -n "$NON_INTERACTIVE" ]; then
    echo "Mode: Non-interactive"
else
    echo "Mode: Interactive"
fi

# Run the output controller
python -m src.networking.run_output_extended --mode $MODE --port $PORT --verbose $VERBOSE $NON_INTERACTIVE $EXTRA_ARGS

# Exit with the same status code as the Python script
exit $? 