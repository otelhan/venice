#!/bin/bash

# Get the node name from command line argument or default to res00
NODE_NAME=${1:-res00}

# Log file for cron execution
LOG_FILE="/home/ven-res0/cron_${NODE_NAME}.log"
exec > "$LOG_FILE" 2>&1

echo "Starting controller in headless mode at $(date)"
echo "Node name: $NODE_NAME"

# Change to project directory
cd /home/ven-res0/venice

# Activate virtual environment
source venv/bin/activate

# Set environment variables for non-GUI operation
export MPLBACKEND=Agg
export PYTHONPATH=.
export PYTHONUNBUFFERED=1

# Run the controller
echo "Running controller with node: $NODE_NAME"
python -m src.run_controller $NODE_NAME
echo "Controller finished with status: $?"