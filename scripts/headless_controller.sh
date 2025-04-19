#!/bin/bash

# Log file
LOG_FILE="/home/ven-res0/headless_controller.log"
exec > "$LOG_FILE" 2>&1

echo "===== Starting Headless Controller ====="
echo "Date: $(date)"
echo "Node: $1"

# Change to project directory
cd /home/ven-res0/venice

# Activate virtual environment
source venv/bin/activate

# Set environment variables for headless operation
export MPLBACKEND=Agg
export PYTHONUNBUFFERED=1
export PYTHONPATH=.

# Run the controller
echo "Running controller with node: $1"
python -m src.run_controller $1
EXIT_CODE=$?

echo "Controller exited with code: $EXIT_CODE"
echo "===== Headless Controller Ended ====="