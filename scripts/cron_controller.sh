#!/bin/bash

# Get the node name from command line argument or default to res00
NODE_NAME=${1:-res00}

# Log file for cron execution
LOG_FILE="/home/ven-res0/cron_${NODE_NAME}.log"
exec > "$LOG_FILE" 2>&1

echo "===== Controller Script Started ====="
echo "Date: $(date)"
echo "Node: $NODE_NAME"
echo "User: $(whoami)"
echo "Current directory: $(pwd)"

# Change to project directory
cd /home/ven-res0/venice
echo "Changed to directory: $(pwd)"

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    echo "Activating virtual environment"
    source venv/bin/activate
    echo "Python: $(which python)"
    echo "Python version: $(python --version 2>&1)"
else
    echo "ERROR: Virtual environment not found at venv/bin/activate"
    exit 1
fi

# Set environment variables for non-GUI operation
export MPLBACKEND=Agg
export PYTHONPATH=.
export PYTHONUNBUFFERED=1

# Run the controller
echo "Running controller with node: $NODE_NAME"
python -m src.run_controller $NODE_NAME
EXIT_CODE=$?
echo "Controller finished with status: $EXIT_CODE"

echo "===== Controller Script Ended ====="
echo "Date: $(date)"
echo "Exit code: $EXIT_CODE"