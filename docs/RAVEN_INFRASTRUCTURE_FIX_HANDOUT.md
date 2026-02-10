# Raven Realtime Infrastructure Fix - Session Handout

**Date:** 2026-02-10  
**Status:** Backend code COMPLETE, Infrastructure routing fix PENDING  
**Priority:** High

---

## 1. CRITICAL CONTEXT

### What's Already Done (DO NOT CHANGE)
- ✅ Backend code is **CORRECT** - all AI/user messages use shared `publish_message_created_event()` helper
- ✅ Event name: `message_created`
- ✅ Room targeting: `doctype="Raven Channel"`, `docname=channel_id` → room `doc:Raven Channel:<channel_id>`
- ✅ Frontend uses `useFrappeDocumentEventListener('Raven Channel', channelID, ...)` - matches backend

### What's Broken (NEEDS FIX)
The issue is **transport/routing**, NOT code logic:

| Environment | Problem | Root Cause |
|-------------|---------|------------|
| **Sandbox** | Browser gets 404 on `/socket.io` | ngrok not forwarding `/socket.io` to port 9000 |
| **Prod** | WebSocket instability | Traefik/nginx routing to Socket.IO server on 9001 |

---

## 2. SANDBOX FIX (Priority - Test Here First)

### Current State
- Socket.IO listens on: `localhost:9000` ✓ (works locally)
- ngrok points to: port 8000 (Frappe web only)
- Result: `https://sysmayal.ngrok.io/socket.io/` returns **404**

### Solution: nginx Multiplexer

**Step 1:** Create nginx config file on sandbox server

```nginx
# /etc/nginx/sites-available/frappe-multiplexer
server {
  listen 8005;

  location / {
    proxy_pass http://127.0.0.1:8000;  # Frappe web
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  location /socket.io/ {
    proxy_pass http://127.0.0.1:9000;  # Socket.IO
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400;
    proxy_send_timeout 86400;
    proxy_buffering off;
  }
}
```

**Step 2:** Enable and start nginx
```bash
sudo ln -s /etc/nginx/sites-available/frappe-multiplexer /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

**Step 3:** Restart ngrok pointing to port 8005
```bash
# Kill existing ngrok
pkill ngrok

# Start new ngrok on multiplexer port
ngrok http 8005
```

**Step 4:** Validate
```bash
# Local test (should already work)
curl "http://localhost:9000/socket.io/?EIO=4&transport=polling" -iv
# Expected: HTTP 200 with JSON handshake

# External test (should work AFTER fix)
curl "https://sysmayal.ngrok.io/socket.io/?EIO=4&transport=polling" -iv
# Expected: HTTP 200 (currently 404)
```

---

## 3. PROD FIX (v2.sysmayal.cloud)

### Current State
- Socket.IO server: `0.0.0.0:9001`
- Public endpoint: `https://v2.sysmayal.cloud/socket.io/`
- Stack: Traefik + nginx sidecar (Docker)

### Solution: nginx Sidecar Config

**nginx.conf for frappe-socketio container:**
```nginx
events { worker_connections 1024; }

http {
  upstream socketio_backend {
    server 172.17.0.1:9001;
  }

  server {
    listen 80;

    location /socket.io/ {
      proxy_pass http://socketio_backend;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_read_timeout 86400;
      proxy_send_timeout 86400;
      proxy_buffering off;
    }
  }
}
```

**Traefik labels for frappe-socketio container:**
```yaml
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.frappe-socketio.rule=Host(`v2.sysmayal.cloud`) && PathPrefix(`/socket.io`)"
  - "traefik.http.routers.frappe-socketio.entrypoints=websecure"
  - "traefik.http.routers.frappe-socketio.tls.certresolver=myresolver"
  - "traefik.http.services.frappe-socketio.loadbalancer.server.port=80"
```

**Important:** Ensure no other router claims `/socket.io` for the same host.

### Prod Validation
```bash
# From host
curl "http://localhost:9001/socket.io/?EIO=4&transport=polling" -iv

# From outside
curl -k "https://v2.sysmayal.cloud/socket.io/?EIO=4&transport=polling" -iv
```

---

## 4. FINAL VALIDATION (Both Environments)

After infrastructure fix, test from `bench console`:

```python
import frappe

# Replace with actual channel ID from your Raven instance
channel_id = "your-channel-id-here"

frappe.publish_realtime(
    "message_created",
    {
        "channel_id": channel_id,
        "sender": frappe.session.user,
        "message_id": "TEST-REALTIME-001",
        "message_details": {
            "text": "Test message from console",
            "message_type": "Text"
        },
    },
    doctype="Raven Channel",
    docname=channel_id,
    after_commit=True,
)
frappe.db.commit()
```

**Expected:** Message appears in Raven UI WITHOUT page refresh.

---

## 5. KEY FILES REFERENCE

| File | Purpose |
|------|---------|
| `/workspace/raven_ai_agent/api/channel_utils.py` | Contains `publish_message_created_event()` helper |
| `/workspace/raven_ai_agent/api/agent.py` | Main AI agent (uses helper) |
| `/workspace/raven_ai_agent/api/agent_V1.py` | Legacy agent (uses helper) |
| `/workspace/raven_ai_agent/channels/raven_channel.py` | Channel handler (uses helper) |
| `/workspace/docs/RAVEN_REALTIME_FIX_HANDOUT.md` | Full code fix documentation |

---

## 6. QUICK REFERENCE

```
┌─────────────────────────────────────────────────────────────┐
│ RAVEN INFRASTRUCTURE FIX - QUICK REFERENCE                  │
├─────────────────────────────────────────────────────────────┤
│ SANDBOX:                                                    │
│   Problem:  ngrok → 8000 only (no socket.io)               │
│   Fix:      nginx on 8005 → routes to 8000 + 9000          │
│   Action:   ngrok http 8005                                 │
├─────────────────────────────────────────────────────────────┤
│ PROD:                                                       │
│   Problem:  Traefik/nginx not routing /socket.io           │
│   Fix:      nginx sidecar + Traefik labels                 │
│   Port:     Socket.IO on 9001                              │
├─────────────────────────────────────────────────────────────┤
│ VALIDATION:                                                 │
│   curl ".../socket.io/?EIO=4&transport=polling"            │
│   Expected: HTTP 200 + JSON handshake                       │
├─────────────────────────────────────────────────────────────┤
│ DO NOT CHANGE:                                              │
│   - Event name (message_created)                            │
│   - Room logic (doctype/docname)                           │
│   - publish_message_created_event() helper                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. NEXT SESSION CHECKLIST

1. [ ] **Sandbox First:** Apply nginx multiplexer config
2. [ ] **Validate Sandbox:** curl test returns 200
3. [ ] **Test Sandbox:** Send AI message, verify real-time delivery
4. [ ] **Prod:** Apply Traefik + nginx sidecar config
5. [ ] **Validate Prod:** curl test returns 200
6. [ ] **Test Prod:** Send AI message, verify real-time delivery

---

*Handout created for session continuity. Backend code is complete and correct. Only infrastructure routing needs to be fixed.*
