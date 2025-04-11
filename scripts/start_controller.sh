# Change to project directory#!/bin/bash

cd "$(dirname "$0")/.."

# Source virtual environment
source venv/bin/activate

# Run controller with node name argument
python -m src.run_controller $1 

