#!/bin/bash
# Check socketio configuration
docker exec n8n-frappe-1 grep -r socket /etc/nginx/ 2>/dev/null || echo "NO_SOCKETIO_CONFIG_IN_NGINX"
echo "---"
# Check what's listening
ss -tlnp | grep -E "8000|9001|80"
echo "---"
# Check if bench serve is running
ps aux | grep "bench serve" | grep -v grep
