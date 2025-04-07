#!/bin/bash
# Script to run the output controller
# This can be used in both operation mode and test mode

# Navigate to the project root directory
cd "$(dirname "$0")/.."

# Check for arguments
MODE="operation"  # Default mode
INTERACTIVE=""    # By default, run in non-interactive mode

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
    --interactive|-i)
      INTERACTIVE=""  # Remove non-interactive flag
      shift
      ;;
    *)
      # Pass any other arguments directly to the Python script
      EXTRA_ARGS="$EXTRA_ARGS $1"
      shift
      ;;
  esac
done

# If not interactive, add the flag
if [ -z "$INTERACTIVE" ]; then
  EXTRA_ARGS="$EXTRA_ARGS --non-interactive"
fi

# Run the output controller
echo "Starting Output Controller in $MODE mode..."
python -m src.networking.run_output_extended --mode $MODE $EXTRA_ARGS

# Exit with the same status code as the Python script
exit $? 