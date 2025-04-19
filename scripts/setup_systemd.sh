#!/bin/bash
# Simple script to set up the systemd service for the reservoir controller
# Usage: ./setup_systemd.sh [node_name]
# Example: ./setup_systemd.sh res00

# Get node name from argument or default to res00
NODE_NAME=${1:-res00}
echo "Setting up systemd service for node: $NODE_NAME"

# Create the systemd user directory
mkdir -p ~/.config/systemd/user/

# Create the service file
cat > ~/.config/systemd/user/reservoir-controller.service << EOF
[Unit]
Description=Reservoir Controller ($NODE_NAME)
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/ven-res0/.Xauthority
Environment=QT_DEBUG_PLUGINS=1
Environment=QT_GRAPHICSSYSTEM=native
Environment=QT_QPA_PLATFORM=xcb
WorkingDirectory=/home/ven-res0/venice
ExecStartPre=/bin/sleep 10
ExecStart=/home/ven-res0/venice/scripts/start_controller.sh $NODE_NAME
Restart=on-failure
RestartSec=10

[Install]
WantedBy=graphical-session.target
EOF

# Enable lingering (allows user services to run after logout)
echo "Enabling user lingering (requires sudo)..."
sudo loginctl enable-linger $(whoami)

# Reload systemd
echo "Reloading systemd user daemon..."
systemctl --user daemon-reload

# Enable the service
echo "Enabling service to start at boot..."
systemctl --user enable reservoir-controller.service

# Start the service
echo "Starting service now..."
systemctl --user start reservoir-controller.service

# Check service status
echo "Service status:"
systemctl --user status reservoir-controller.service

echo ""
echo "Setup complete! The controller will now start automatically at boot."
echo "To check logs: journalctl --user -u reservoir-controller.service -f"
echo "To check status: systemctl --user status reservoir-controller.service"