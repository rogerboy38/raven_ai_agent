#!/bin/bash
# ============================================================
# 🤖 bot-iot-l01 — Service Installer
# ============================================================
# Installs and enables all Raven services for boot persistence:
#   1. raven-weight   — Flask weight capture web app (:5000)
#   2. raven-ngrok    — ngrok tunnel (bot1.sysmayal.ngrok.io)
#   3. raven-claw     — Claw Code AI agent
#   4. raven-watchdog — Network watchdog (every 2 min)
#
# Usage:
#   sudo bash services/install_services.sh
#
# After install:
#   sudo systemctl status raven-weight raven-ngrok raven-claw
#   journalctl -u raven-weight -f          # live weight app logs
#   journalctl -u raven-ngrok -f           # live ngrok logs
#   journalctl -u raven-claw -f            # live agent logs
#   journalctl -t raven-watchdog --since today  # watchdog events
# ============================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SERVICES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAVEN_DIR="$(dirname "$SERVICES_DIR")"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  🤖 bot-iot-l01 — Service Installer${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Must run as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}ERROR: Must run as root (sudo)${NC}"
    exit 1
fi

# ---- Pre-flight checks ----
echo -e "${YELLOW}[1/6] Pre-flight checks...${NC}"

# Check Flask app
if [ ! -f "$RAVEN_DIR/rpi_client/web_app.py" ]; then
    echo -e "${RED}ERROR: web_app.py not found at $RAVEN_DIR/rpi_client/web_app.py${NC}"
    exit 1
fi
echo "  ✅ web_app.py found"

# Check venv
if [ ! -f "$RAVEN_DIR/raven-env/bin/python3" ]; then
    echo -e "${RED}ERROR: Python venv not found. Run: python3 -m venv $RAVEN_DIR/raven-env${NC}"
    exit 1
fi
echo "  ✅ raven-env venv found"

# Check ngrok
if ! command -v ngrok &>/dev/null; then
    echo -e "${RED}ERROR: ngrok not installed${NC}"
    exit 1
fi
echo "  ✅ ngrok $(ngrok version 2>/dev/null | head -1)"

# Check claw
if [ ! -f "/home/admin/claw-code/rust/target/debug/claw" ]; then
    echo -e "${YELLOW}WARNING: Claw Code binary not found — skipping raven-claw service${NC}"
    SKIP_CLAW=1
fi
[ -z "$SKIP_CLAW" ] && echo "  ✅ claw binary found"

# Check env files
if [ ! -f "$RAVEN_DIR/rpi_client/.env" ]; then
    echo -e "${RED}ERROR: rpi_client/.env not found${NC}"
    exit 1
fi
echo "  ✅ rpi_client/.env"

if [ -z "$SKIP_CLAW" ] && [ ! -f "$SERVICES_DIR/claw.env" ]; then
    echo -e "${YELLOW}WARNING: claw.env not found — skipping raven-claw service${NC}"
    SKIP_CLAW=1
fi
[ -z "$SKIP_CLAW" ] && echo "  ✅ claw.env"

# ---- Stop old processes ----
echo ""
echo -e "${YELLOW}[2/6] Stopping old processes...${NC}"

# Kill manual web_app.py if running
pkill -f "python3 rpi_client/web_app.py" 2>/dev/null && echo "  Stopped manual web_app.py" || echo "  No manual web_app.py running"
pkill -f "python3 web_app.py" 2>/dev/null || true

# Kill manual ngrok if running
pkill -f "ngrok http.*5000" 2>/dev/null && echo "  Stopped manual ngrok" || echo "  No manual ngrok running"

# Stop old systemd services if they exist
systemctl stop raven-weight.service 2>/dev/null || true
systemctl stop raven-ngrok.service 2>/dev/null || true
systemctl stop raven-claw.service 2>/dev/null || true
systemctl stop raven-watchdog.timer 2>/dev/null || true
systemctl stop raven-bot.service 2>/dev/null || true
echo "  Stopped existing systemd services"

# ---- Make scripts executable ----
echo ""
echo -e "${YELLOW}[3/6] Setting permissions...${NC}"

chmod +x "$SERVICES_DIR/network_watchdog.sh"
chmod 600 "$SERVICES_DIR/claw.env" 2>/dev/null || true
echo "  ✅ Permissions set"

# ---- Install systemd units ----
echo ""
echo -e "${YELLOW}[4/6] Installing systemd units...${NC}"

cp "$SERVICES_DIR/raven-weight.service" /etc/systemd/system/
echo "  📦 raven-weight.service"

cp "$SERVICES_DIR/raven-ngrok.service" /etc/systemd/system/
echo "  📦 raven-ngrok.service"

if [ -z "$SKIP_CLAW" ]; then
    cp "$SERVICES_DIR/raven-claw.service" /etc/systemd/system/
    echo "  📦 raven-claw.service"
fi

cp "$SERVICES_DIR/raven-watchdog.service" /etc/systemd/system/
cp "$SERVICES_DIR/raven-watchdog.timer" /etc/systemd/system/
echo "  📦 raven-watchdog.timer"

# Disable old raven-bot.service if it exists
systemctl disable raven-bot.service 2>/dev/null || true

systemctl daemon-reload
echo "  ✅ systemd daemon reloaded"

# ---- Enable services ----
echo ""
echo -e "${YELLOW}[5/6] Enabling services for boot...${NC}"

systemctl enable raven-weight.service
echo "  ✅ raven-weight → enabled (boot)"

systemctl enable raven-ngrok.service
echo "  ✅ raven-ngrok → enabled (boot)"

if [ -z "$SKIP_CLAW" ]; then
    systemctl enable raven-claw.service
    echo "  ✅ raven-claw → enabled (boot)"
fi

systemctl enable raven-watchdog.timer
echo "  ✅ raven-watchdog.timer → enabled (boot)"

# ---- Start services now ----
echo ""
echo -e "${YELLOW}[6/6] Starting services...${NC}"

systemctl start raven-weight.service
sleep 2

# Verify Flask is up before starting ngrok
if curl -sf http://localhost:5000/api/status >/dev/null 2>&1; then
    echo "  ✅ raven-weight started (Flask responding on :5000)"
else
    echo "  ⚠️  raven-weight started (Flask not yet responding — may take a moment)"
fi

systemctl start raven-ngrok.service
echo "  ✅ raven-ngrok started"

if [ -z "$SKIP_CLAW" ]; then
    systemctl start raven-claw.service
    echo "  ✅ raven-claw started"
fi

systemctl start raven-watchdog.timer
echo "  ✅ raven-watchdog.timer started"

# ---- Summary ----
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  🎉 All services installed & running!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Service status:"
echo "───────────────────────────────────────"

for svc in raven-weight raven-ngrok raven-claw; do
    if [ "$svc" = "raven-claw" ] && [ -n "$SKIP_CLAW" ]; then
        echo "  $svc: SKIPPED"
        continue
    fi
    STATUS=$(systemctl is-active $svc.service 2>/dev/null || echo "inactive")
    if [ "$STATUS" = "active" ]; then
        echo -e "  ${GREEN}●${NC} $svc: ${GREEN}$STATUS${NC}"
    else
        echo -e "  ${RED}●${NC} $svc: ${RED}$STATUS${NC}"
    fi
done

TIMER_STATUS=$(systemctl is-active raven-watchdog.timer 2>/dev/null || echo "inactive")
echo -e "  ${GREEN}●${NC} raven-watchdog.timer: ${GREEN}$TIMER_STATUS${NC}"

echo ""
echo "🌐 Weight UI: https://bot1.sysmayal.ngrok.io"
echo ""
echo "Useful commands:"
echo "  journalctl -u raven-weight -f       # live weight app logs"
echo "  journalctl -u raven-ngrok -f        # live ngrok logs"
echo "  journalctl -u raven-claw -f         # live agent logs"
echo "  journalctl -t raven-watchdog        # watchdog events"
echo "  sudo systemctl restart raven-weight # restart weight app"
echo "  sudo systemctl restart raven-ngrok  # restart tunnel"
echo ""
echo "🔒 These services will auto-start on reboot and auto-recover from:"
echo "   • Power outages"
echo "   • Network drops (watchdog restarts ngrok within 2 min)"
echo "   • Process crashes (systemd auto-restart within 5-30 sec)"
echo ""
