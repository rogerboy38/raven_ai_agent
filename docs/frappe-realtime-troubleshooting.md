# Frappe Realtime WebSocket Troubleshooting - Session Summary

## Issue
"Realtime events are not working. Please try refreshing the page" error after migrating Frappe from frappe.cloud to Hostinger VPS.

## Environment
- **Site**: v2.sysmayal.cloud
- **Stack**: Frappe + Traefik (Docker) + systemd services
- **Database**: Remote MariaDB (187.77.2.74:3307)

---

## What Was Done This Session

### 1. Verified Backend Components Working
- ✅ Redis socketio running on port 12000 (`redis-cli ping` returns PONG)
- ✅ Frappe socketio service running on port 9001
- ✅ Redis pub/sub working (tested with `frappe.publish_realtime()`)
- ✅ Site config correct (`socketio_port: 9001`, `redis_socketio: redis://localhost:12000`)

### 2. Fixed nginx Site Name Header
```bash
# Changed X-Frappe-Site-Name from old domain to new domain
sudo sed -i 's/sysmayal2.v.frappe.cloud/v2.sysmayal.cloud/g' /etc/nginx/sites-available/v2.sysmayal.cloud
```

### 3. Replaced socat Proxy with nginx (WebSocket-capable)
**Problem**: socat doesn't properly handle HTTP/WebSocket protocol upgrades.

**Solution**: Created nginx container with proper WebSocket proxy config:

```bash
# nginx config at /tmp/nginx-socketio.conf
events {
    worker_connections 1024;
}
http {
    upstream socketio {
        server 172.17.0.1:9001;
    }
    server {
        listen 80;
        location / {
            proxy_pass http://socketio;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_read_timeout 86400;
        }
    }
}

# Running container
docker run -d --name frappe-socketio \
  -v /tmp/nginx-socketio.conf:/etc/nginx/nginx.conf:ro \
  -l "traefik.enable=true" \
  -l "traefik.http.routers.frappe-socketio.rule=Host(\`v2.sysmayal.cloud\`) && PathPrefix(\`/socket.io\`)" \
  -l "traefik.http.routers.frappe-socketio.entrypoints=websecure" \
  -l "traefik.http.routers.frappe-socketio.tls=true" \
  -l "traefik.http.routers.frappe-socketio.tls.certresolver=mytlschallenge" \
  -l "traefik.http.routers.frappe-socketio.priority=100" \
  -l "traefik.http.services.frappe-socketio.loadbalancer.server.port=80" \
  --network n8n_default \
  nginx:alpine
```

### 4. Current Status
- ✅ WebSocket upgrade working (nginx logs show `101` status code)
- ✅ Polling transport working
- ❌ Browser still shows realtime error (WebSocket closes before establishing)

---

## Remaining Issue

The WebSocket upgrade succeeds at the server level, but the browser connection fails:
```
WebSocket connection to 'wss://v2.sysmayal.cloud/socket.io/?EIO=4&transport=websocket&sid=...' failed: 
WebSocket is closed before the connection is established.
```

### Possible Causes to Investigate Next Session:
1. **Session mismatch** - The `sid` from polling doesn't match when upgrading to WebSocket
2. **Traefik HTTP/2 issue** - Even with `maxConcurrentStreams=0`, there may be lingering issues
3. **Sticky sessions needed** - WebSocket upgrade needs to hit the same backend instance
4. **Frappe socketio site verification** - The socketio server may be rejecting connections for wrong site name

---

## Quick Diagnostic Commands

```bash
# Check all services
sudo systemctl status frappe-bench
sudo systemctl status frappe-socketio
redis-cli -p 12000 ping

# Check Docker containers
docker ps | grep -E "frappe|socketio|traefik"

# Test socket.io polling
curl -s "https://v2.sysmayal.cloud/socket.io/?EIO=4&transport=polling"

# Test WebSocket upgrade
curl -i --http1.1 -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Sec-WebSocket-Version: 13" \
  "https://v2.sysmayal.cloud/socket.io/?EIO=4&transport=websocket"

# Check nginx proxy logs
docker logs frappe-socketio -f

# Check Frappe socketio logs
sudo journalctl -u frappe-socketio -f

# Test from bench console
cd ~/frappe-bench && bench --site v2.sysmayal.cloud console
# Then: frappe.publish_realtime("test", {"msg": "hello"}, user="Administrator")
```

---

## Key Files & Configs

| File | Purpose |
|------|---------|
| `/etc/nginx/sites-available/v2.sysmayal.cloud` | nginx site config (not actively used, Traefik handles SSL) |
| `/tmp/nginx-socketio.conf` | WebSocket proxy config for Docker nginx |
| `~/frappe-bench/sites/v2.sysmayal.cloud/site_config.json` | Site configuration |
| `/etc/systemd/system/frappe-bench.service` | Frappe main service |
| `/etc/systemd/system/frappe-socketio.service` | Frappe socketio service |

---

## Architecture

```
Browser
   │
   ▼ (HTTPS/WSS)
Traefik (Docker: n8n-traefik-1)
   │
   ├── /socket.io/* ──► nginx proxy (Docker: frappe-socketio) ──► Host:9001 (frappe-socketio systemd)
   │                                                                    │
   │                                                                    ▼
   │                                                              Redis :12000
   │
   └── /* ──► socat proxy (Docker: n8n-frappe-1) ──► Host:8000 (frappe-bench systemd)
```

---

## Next Steps for Next Session

1. **Check Traefik sticky sessions** - May need to add sticky session middleware for WebSocket
2. **Debug Frappe socketio service** - Add debug logging to see why connections are rejected
3. **Test without Traefik** - Temporarily expose port 9001 directly to isolate the issue
4. **Check if issue exists on frappe.cloud sandbox** - You mentioned sandbox has same issue, suggesting DB/config problem
5. **Review Raven app settings** - The error appears on Raven, may be app-specific

---

## Important Notes

- The issue also appears on the sandbox pointing to the same database
- This suggests the problem might be in the database configuration or a Frappe setting, not just the proxy setup
- WebSocket upgrade IS working at the protocol level (101 status), but application-level handshake fails
