#!/bin/bash
# Simple script to run the output controller in non-interactive mode

# Navigate to the project root directory
cd "$(dirname "$0")/.."

# Source the virtual environment
source venv/bin/activate

# Run the output controller with specified arguments
# and pass any additional arguments from command line
python -m src.networking.run_output_extended --mode operation --non-interactive --no-ack "$@"

# Exit with the same status code as the Python script
exit $? 