#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Get the repository root directory (one level up from scripts)
REPO_DIR="$( cd "$SCRIPT_DIR/.." &> /dev/null && pwd )"

# Function to handle cleanup on script exit
cleanup() {
    echo "Cleaning up..."
    # Kill the tmux session more forcefully
    tmux kill-session -t venice 2>/dev/null
    # Kill any remaining python processes started by this script
    pkill -f "python -m tests.test_video_input"
    pkill -f "python -m src.networking.reservoir_builder"
}

# Set up cleanup trap for various signals
trap cleanup EXIT SIGINT SIGTERM

# Navigate to the repository directory
cd "$REPO_DIR"

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "tmux is not installed. Please install it first:"
    echo "sudo apt-get install tmux"
    exit 1
fi

# Kill any existing venice session and processes
cleanup

# Create a new tmux session named 'venice'
tmux new-session -d -s venice

# Split the window horizontally
tmux split-window -h

# Configure the first pane (video input)
tmux select-pane -t 0
# Add trap to monitor video input exit
tmux send-keys "source venv/bin/activate && echo 'Starting video input...' && python -m tests.test_video_input --fullscreen; tmux kill-session -t venice" C-m

# Configure the second pane (reservoir builder)
tmux select-pane -t 1
tmux send-keys "source venv/bin/activate && echo 'Starting reservoir builder...' && python -m src.networking.reservoir_builder" C-m

# Set the layout to even horizontal split
tmux select-layout even-horizontal

# Display startup message
echo "Starting Venice system..."
echo "Video input and reservoir builder will start in separate panes."
echo "Controls:"
echo "  Video Input (left pane):"
echo "    's' - Select all ROIs"
echo "    'r' - Select single ROI"
echo "    't' - Toggle ROI display"
echo "    'f' - Toggle fullscreen"
echo "    'q' - Quit"
echo ""
echo "Tmux commands:"
echo "  Ctrl+B then D - Detach from tmux"
echo "  'tmux attach -t venice' - Reattach"
echo "  'tmux kill-session -t venice' - Stop all processes"
echo "  'pkill -f \"python -m tests.test_video_input\"' - Stop video input"
echo "  'pkill -f \"python -m src.networking.reservoir_builder\"' - Stop reservoir builder"

# Attach to the session
tmux attach-session -t venice

# Run cleanup on script exit
cleanup 