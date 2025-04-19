#!/bin/bash

# Controller startup script with X11 env setup
LOG_FILE="/home/ven-res0/controller-x11.log"
exec > "$LOG_FILE" 2>&1

echo "===== X11 Controller Startup ====="
echo "Start time: $(date)"
echo "User: $(whoami)"

# Wait for display to be ready
sleep 5

# Get the current user ID
USER_ID=$(id -u)

# Export essential X11 environment
export DISPLAY=:0
export XAUTHORITY="/home/ven-res0/.Xauthority"
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$USER_ID/bus"
export XDG_RUNTIME_DIR="/run/user/$USER_ID"

# Qt-specific configuration
export QT_QPA_PLATFORM=xcb
export QT_DEBUG_PLUGINS=1

echo "Display env: DISPLAY=$DISPLAY"
echo "Auth file: XAUTHORITY=$XAUTHORITY"
echo "D-Bus: $DBUS_SESSION_BUS_ADDRESS"
echo "XDG runtime: $XDG_RUNTIME_DIR"

# Try to set access control
xhost +local:ven-res0 || echo "xhost failed (continuing)"

echo "Entering project directory"
cd /home/ven-res0/venice

echo "Activating virtual environment"
source venv/bin/activate

echo "Starting controller node: $1"
python -m src.run_controller $1
echo "Controller exited with code: $?"