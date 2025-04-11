#!/bin/bash

cd "$(dirname "$0")/.."

# Wait for X server to start
sleep 10

# Set display and X authority for GUI windows
export DISPLAY=:0
export XAUTHORITY=/home/pi/.Xauthority
xhost +local:

# Source virtual environment
source venv/bin/activate

# Run controller with node name argument
python -m src.run_controller $1 

