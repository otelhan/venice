#!/bin/bash
# Script to run the output controller
# This can be used in both operation mode and test mode

# Navigate to the project root directory
cd "$(dirname "$0")/.."

# Check for arguments
MODE="operation"  # Default mode

# Process command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --test|-t)
      MODE="test"
      shift
      ;;
    --operation|-o)
      MODE="operation"
      shift
      ;;
    *)
      # Pass any other arguments directly to the Python script
      EXTRA_ARGS="$EXTRA_ARGS $1"
      shift
      ;;
  esac
done

# Run the output controller
echo "Starting Output Controller in $MODE mode..."
python -m src.networking.run_output_extended --mode $MODE $EXTRA_ARGS

# Exit with the same status code as the Python script
exit $? 