#!/bin/bash

# Set path to virtual environment
VENV=/home/pi/venice/venv

# Activate virtual environment
export PYTHONPATH=/home/pi/venice
source $VENV/bin/activate

# Change to project directory
cd /home/pi/venice

# Run controller with node name argument
$VENV/bin/python -m src.run_controller $1 