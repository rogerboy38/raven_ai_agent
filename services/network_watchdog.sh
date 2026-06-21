#!/bin/bash
# Raven Network Watchdog — bot-iot-l01
# Checks connectivity and restarts services if needed
# Called by raven-watchdog.timer every 2 minutes

STATE_FILE="/tmp/raven_network_state"
LOG_TAG="raven-watchdog"

log() { logger -t "$LOG_TAG" "$1"; }

# Test connectivity — try gateway first, then DNS, then ERPNext
check_network() {
    # 1. Gateway reachable?
    GATEWAY=$(ip route | awk '/default/ {print $3}' | head -1)
    if [ -n "$GATEWAY" ] && ping -c1 -W2 "$GATEWAY" >/dev/null 2>&1; then
        return 0
    fi

    # 2. DNS works?
    if ping -c1 -W3 8.8.8.8 >/dev/null 2>&1; then
        return 0
    fi

    # 3. Can reach ERPNext?
    if curl -sf --max-time 5 https://sandbox.sysmayal.cloud >/dev/null 2>&1; then
        return 0
    fi

    return 1
}

# Current state
PREV_STATE="up"
[ -f "$STATE_FILE" ] && PREV_STATE=$(cat "$STATE_FILE")

if check_network; then
    echo "up" > "$STATE_FILE"

    if [ "$PREV_STATE" = "down" ]; then
        log "🟢 Network RECOVERED — restarting ngrok tunnel"
        # ngrok needs a restart after network drop; weight app auto-reconnects
        systemctl restart raven-ngrok.service 2>/dev/null
        log "ngrok restarted after network recovery"
    fi

    # Health check: make sure services are actually running
    if ! systemctl is-active --quiet raven-weight.service; then
        log "⚠️ raven-weight not running — starting"
        systemctl start raven-weight.service
    fi

    if ! systemctl is-active --quiet raven-ngrok.service; then
        log "⚠️ raven-ngrok not running — starting"
        systemctl start raven-ngrok.service
    fi

else
    echo "down" > "$STATE_FILE"

    if [ "$PREV_STATE" = "up" ]; then
        log "🔴 Network DOWN — services will auto-restart when connectivity returns"
    fi
fi
