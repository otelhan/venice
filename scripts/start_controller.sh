# Change to project directory#!/bin/bash

cd /home/pi/venice

# Source virtual environment
source /home/pi/venice/venv/bin/activate

# Run controller with node name argument
python -m src.run_controller $1 