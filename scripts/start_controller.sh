#!/bin/bash

# Source virtual environment
source /home/pi/venice/venv/bin/activate

# Change to project directory
cd /home/pi/venice

# Run controller with node name argument
python -m src.run_controller $1 