#!/bin/bash
# Socket.IO Connectivity Diagnostic Script
# Run this on the server to verify routing

echo "=== Socket.IO Diagnostic ==="
echo ""

# 1. Check if Socket.IO is running locally
echo "1. Testing local Socket.IO (port 9000)..."
LOCAL_RESPONSE=$(curl -s "http://localhost:9000/socket.io/?EIO=4&transport=polling" 2>&1)
if echo "$LOCAL_RESPONSE" | grep -q '"sid"'; then
    echo "   ✅ Local Socket.IO is responding correctly"
else
    echo "   ❌ Local Socket.IO NOT responding. Check if frappe-socketio is running."
    echo "   Response: $LOCAL_RESPONSE"
fi
echo ""

# 2. Check external URL (ngrok or production)
echo "2. Testing external Socket.IO endpoint..."
if [ -n "$1" ]; then
    EXTERNAL_URL="$1"
else
    # Try to detect from site_config
    EXTERNAL_URL=$(grep -o '"host_name"[[:space:]]*:[[:space:]]*"[^"]*"' ~/frappe-bench/sites/*/site_config.json 2>/dev/null | head -1 | cut -d'"' -f4)
    if [ -z "$EXTERNAL_URL" ]; then
        EXTERNAL_URL="https://sysmayal.ngrok.io"
    fi
fi

echo "   Testing: $EXTERNAL_URL/socket.io/?EIO=4&transport=polling"
EXTERNAL_RESPONSE=$(curl -s "$EXTERNAL_URL/socket.io/?EIO=4&transport=polling" 2>&1)
if echo "$EXTERNAL_RESPONSE" | grep -q '"sid"'; then
    echo "   ✅ External Socket.IO is accessible"
else
    echo "   ❌ External Socket.IO NOT accessible (likely 404 or routing issue)"
    echo "   Response: $(echo "$EXTERNAL_RESPONSE" | head -c 200)"
fi
echo ""

# 3. Check nginx multiplexer (if on sandbox)
echo "3. Checking nginx multiplexer on port 8005..."
NGINX_RESPONSE=$(curl -s "http://localhost:8005/socket.io/?EIO=4&transport=polling" 2>&1)
if echo "$NGINX_RESPONSE" | grep -q '"sid"'; then
    echo "   ✅ nginx multiplexer is routing /socket.io/ correctly"
else
    echo "   ⚠️  nginx multiplexer not configured or not routing /socket.io/"
    echo "   This is required for ngrok to work with Socket.IO"
fi
echo ""

# 4. Check what processes are listening
echo "4. Checking listening ports..."
echo "   Port 9000 (Socket.IO):"
ss -tlnp 2>/dev/null | grep ":9000" || echo "   Not listening on 9000"
echo "   Port 8000 (Frappe web):"
ss -tlnp 2>/dev/null | grep ":8000" || echo "   Not listening on 8000"
echo "   Port 8005 (nginx mux):"
ss -tlnp 2>/dev/null | grep ":8005" || echo "   Not listening on 8005"
echo ""

echo "=== Diagnostic Complete ==="
echo ""
echo "If external Socket.IO fails but local works:"
echo "  - Sandbox: Set up nginx multiplexer on 8005, point ngrok there"
echo "  - VPS: Check Traefik/nginx routing for /socket.io/ path"
echo ""
echo "See: raven_ai_agent/docs/PARALLEL_TEAM_INITIAL_REPORT.md for fix instructions"
