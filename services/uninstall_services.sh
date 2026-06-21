#!/bin/bash
# Uninstall all Raven services
# Usage: sudo bash services/uninstall_services.sh

set -e

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Must run as root (sudo)"
    exit 1
fi

echo "Stopping and disabling Raven services..."

for svc in raven-weight raven-ngrok raven-claw; do
    systemctl stop $svc.service 2>/dev/null || true
    systemctl disable $svc.service 2>/dev/null || true
    rm -f /etc/systemd/system/$svc.service
    echo "  Removed $svc.service"
done

systemctl stop raven-watchdog.timer 2>/dev/null || true
systemctl disable raven-watchdog.timer 2>/dev/null || true
rm -f /etc/systemd/system/raven-watchdog.timer
rm -f /etc/systemd/system/raven-watchdog.service
echo "  Removed raven-watchdog.timer + service"

systemctl daemon-reload

echo ""
echo "✅ All Raven services removed."
echo "   Source files in services/ are untouched."
