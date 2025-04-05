#!/bin/bash
# Script to run the output controller
# This can be used in both operation mode and test mode

# Navigate to the project root directory
cd "$(dirname "$0")/.."

# Run the output controller
echo "Starting Output Controller..."
python -m src.networking.run_output_extended

# Exit with the same status code as the Python script
exit $? 