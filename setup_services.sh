#!/bin/bash
# Setup script for Frappe systemd services

# Move service files
sudo mv /home/frappe/frappe-bench.service /etc/systemd/system/
sudo mv /home/frappe/frappe-socketio.service /etc/systemd/system/

# Set permissions
sudo chmod 644 /etc/systemd/system/frappe-bench.service
sudo chmod 644 /etc/systemd/system/frappe-socketio.service

# Reload systemd
sudo systemctl daemon-reload

# Enable services to start on boot
sudo systemctl enable frappe-bench.service
sudo systemctl enable frappe-socketio.service

# Stop any existing bench serve processes
pkill -f "bench serve" 2>/dev/null || true
pkill -f "socketio.js" 2>/dev/null || true

# Start the services
sudo systemctl start frappe-bench.service
sleep 3
sudo systemctl start frappe-socketio.service

# Check status
echo "=== Frappe Bench Status ==="
sudo systemctl status frappe-bench.service --no-pager
echo ""
echo "=== Frappe SocketIO Status ==="
sudo systemctl status frappe-socketio.service --no-pager

echo ""
echo "SETUP_COMPLETE"
