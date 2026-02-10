# Frappe v16 WebSocket/Realtime Fix Summary

## Date: February 2025
## Environment: Frappe v16 on Hostinger VPS with Traefik (Docker)

---

## Problem Statement
After migrating from frappe.cloud to a Hostinger VPS, the Frappe instance displayed:
> "Realtime events are not working. Please try refreshing the page."

This error persisted despite Redis and frappe-socketio services running correctly.

---

## Root Cause Analysis

### What Was Working
- Redis service: `redis-cli ping` returned `PONG`
- frappe-socketio service: Running on port 9001
- HTTP polling endpoint: `curl` to `/socket.io/?EIO=4&transport=polling` returned valid session ID
- Backend configuration: `bench console` tests confirmed Redis pub/sub working

### What Was Failing
- **WebSocket upgrade requests were hanging/failing**
- The `socat` container used as a TCP proxy between Traefik and frappe-socketio was **not handling WebSocket protocol upgrades**

### Technical Explanation
WebSocket connections start as HTTP requests with an "Upgrade" header. The server must respond with HTTP 101 (Switching Protocols) to establish the WebSocket connection. `socat` is a simple TCP relay that doesn't understand HTTP headers, so it couldn't properly handle this protocol upgrade mechanism.

---

## Architecture (Before Fix)
```
Browser → Traefik (Docker) → socat container → Host frappe-socketio (port 9001)
                              ↑
                              └── PROBLEM: socat doesn't handle WebSocket upgrades
```

---

## The Fix

### Solution: Replace `socat` with `nginx` as WebSocket Proxy

1. **Created nginx configuration** (`/tmp/nginx-socketio.conf`):
```nginx
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
            proxy_send_timeout 86400;
        }
    }
}
```

2. **Stopped the old socat container**:
```bash
docker stop frappe-socketio
docker rm frappe-socketio
```

3. **Created new nginx proxy container**:
```bash
docker run -d \
  --name frappe-socketio \
  --network n8n_default \
  --label "traefik.enable=true" \
  --label "traefik.http.routers.socketio.rule=Host(\`v2.sysmayal.cloud\`) && PathPrefix(\`/socket.io\`)" \
  --label "traefik.http.routers.socketio.entrypoints=websecure" \
  --label "traefik.http.routers.socketio.tls.certresolver=myresolver" \
  --label "traefik.http.services.socketio.loadbalancer.server.port=80" \
  -v /tmp/nginx-socketio.conf:/etc/nginx/nginx.conf:ro \
  nginx:alpine
```

---

## Architecture (After Fix)
```
Browser → Traefik (Docker) → nginx container → Host frappe-socketio (port 9001)
                              ↑
                              └── FIXED: nginx properly handles WebSocket upgrades
```

---

## Verification Commands

### Test HTTP Polling (should return session ID):
```bash
curl -s "https://v2.sysmayal.cloud/socket.io/?EIO=4&transport=polling" | head -1
```

### Test WebSocket Upgrade (look for 101 status in container logs):
```bash
curl -s -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  "https://v2.sysmayal.cloud/socket.io/?EIO=4&transport=websocket" &
sleep 2
docker logs frappe-socketio --tail 10
```

### Check Container Status:
```bash
docker ps | grep frappe-socketio
docker logs frappe-socketio
```

---

## Other Fixes Applied During Troubleshooting

### 1. Nginx Site Config (Secondary Fix)
Fixed incorrect site name in `/etc/nginx/sites-enabled/v2.sysmayal.cloud`:
```bash
sudo sed -i 's/sysmayal2.v.frappe.cloud/v2.sysmayal.cloud/g' /etc/nginx/sites-enabled/v2.sysmayal.cloud
```
Note: This Nginx config was likely from a previous setup and not actively used (Traefik is the primary proxy).

---

## Important Configuration Files

| File | Purpose |
|------|---------|
| `~/frappe-bench/sites/v2.sysmayal.cloud/site_config.json` | Frappe site config (socketio_port: 9001) |
| `/tmp/nginx-socketio.conf` | Nginx WebSocket proxy config |
| Docker labels on `frappe-socketio` container | Traefik routing rules |

---

## Next Steps / If Issues Persist

1. **Clear browser cache** or test in a fresh incognito window
2. **Check container is running**: `docker ps | grep frappe-socketio`
3. **View nginx proxy logs**: `docker logs frappe-socketio`
4. **Restart services**:
   ```bash
   sudo systemctl restart frappe-bench
   sudo systemctl restart frappe-socketio
   docker restart frappe-socketio
   ```

5. **If container was removed**, recreate it using the docker run command above

---

## Making the Fix Permanent

To ensure the nginx proxy container survives server reboots, add it to a docker-compose file or create a systemd service:

### Option 1: Add to existing docker-compose.yml
```yaml
services:
  frappe-socketio-proxy:
    image: nginx:alpine
    container_name: frappe-socketio
    restart: unless-stopped
    volumes:
      - /path/to/nginx-socketio.conf:/etc/nginx/nginx.conf:ro
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.socketio.rule=Host(`v2.sysmayal.cloud`) && PathPrefix(`/socket.io`)"
      - "traefik.http.routers.socketio.entrypoints=websecure"
      - "traefik.http.routers.socketio.tls.certresolver=myresolver"
      - "traefik.http.services.socketio.loadbalancer.server.port=80"
    networks:
      - n8n_default
```

### Option 2: Move nginx config to permanent location
```bash
sudo mv /tmp/nginx-socketio.conf /etc/nginx/nginx-socketio.conf
# Then update the docker run command to use -v /etc/nginx/nginx-socketio.conf:/etc/nginx/nginx.conf:ro
```

---

## Summary

| Component | Status | Notes |
|-----------|--------|-------|
| Redis | ✅ Working | Service running, pub/sub functional |
| frappe-socketio | ✅ Working | Node service on port 9001 |
| Traefik | ✅ Working | Routing configured correctly |
| WebSocket Proxy | ✅ Fixed | Replaced socat with nginx |
| Browser Connection | ⚠️ Verify | Clear cache and test |

---

*Document generated: February 2025*
*For: Frappe v16 on v2.sysmayal.cloud*
