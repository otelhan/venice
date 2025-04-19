#!/bin/bash
# Headless script to run the output controller
# This can be used for automated startup via systemd

# Change to the project root directory first
cd "$(dirname "$0")/.."

# Source the virtual environment
source venv/bin/activate

# Create log directory and file
LOG_DIR="$(pwd)/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/headless_output_$(date +%Y%m%d_%H%M%S).log"
exec > "$LOG_FILE" 2>&1

echo "===== Starting Headless Output Controller ====="
echo "Date: $(date)"
echo "Working directory: $(pwd)"

# Check for arguments
MODE="operation"  # Default mode
INTERACTIVE=""    # By default, run in non-interactive mode
EXTRA_ARGS=""     # Extra arguments for the Python script

# Process command line arguments - same as original script
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
EXIT_CODE=$?

echo "Output Controller exited with code: $EXIT_CODE"
echo "===== Headless Output Controller Ended ====="
echo "End time: $(date)"

# Exit with the same status code as the Python script
exit $EXIT_CODE