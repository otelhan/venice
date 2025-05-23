#!/bin/bash
# Headless script to run the output controller
# This is almost identical to output.sh but with logging

# Navigate to the project root directory
cd "$(dirname "$0")/.."

# Source the virtual environment
source venv/bin/activate

# Create log file
LOG_FILE="$(pwd)/logs/headless_output_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$(dirname $LOG_FILE)"

# Redirect output to log file AND terminal
exec > >(tee -a "$LOG_FILE") 2>&1

# Check for arguments - IDENTICAL to output.sh from here
MODE="operation"  # Default mode
INTERACTIVE=""    # By default, run in non-interactive mode
EXTRA_ARGS=""     # Initialize EXTRA_ARGS

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

# Run the output controller - IDENTICAL to output.sh
echo "Starting Output Controller in $MODE mode..."
python -m src.networking.run_output_extended --mode $MODE $EXTRA_ARGS

# Exit with the same status code as the Python script
exit $?