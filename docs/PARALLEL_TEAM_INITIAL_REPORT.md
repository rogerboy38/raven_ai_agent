# Raven Realtime - Current Status & Fix Guidelines
## Report from Parallel Team - 2026-02-10 (Earlier Report)

> **Source**: Parallel team initial analysis
> **Purpose**: Fix guidelines for Raven realtime transport and routing issues

---

## 1. Summary

**Backend code for Raven realtime is correct and already fixed:**
- All AI and user messages now call a shared helper that publishes `message_created` with the right doctype, docname and payload.

**The remaining issues are transport and routing:**

| Environment | Problem | Root Cause |
|-------------|---------|------------|
| **Production** | WebSocket/polling stability | Traefik/nginx routing to Socket.IO server |
| **Sandbox** | Browser gets 404 on `/socket.io` | ngrok not forwarding to Socket.IO port |

> **If the team fixes routing according to the guidelines below, the "Realtime events are not working" banner should disappear and messages will appear in the UI without refresh.**

---

## 2. What is Already Correct in Raven

From `RAVEN_REALTIME_FIX_HANDOUT.md`:

- **Correct event name**: `message_created`
- **Correct room targeting**: `doctype="Raven Channel"`, `docname=channel_id` → room `doc:Raven Channel:<channel_id>`

**Correct payload:**
```python
frappe.publish_realtime(
    "message_created",
    {
        "channel_id": channel_id,
        "sender": frappe.session.user,
        "message_id": message_doc.name,
        "message_details": _get_message_details(message_doc),
    },
    doctype="Raven Channel",
    docname=channel_id,
    after_commit=True,
)
```

- All message sources (agent, v1 agent, channel handler) now call the shared `publish_message_created_event()` helper.
- **Frontend**: Uses `useFrappeDocumentEventListener('Raven Channel', channelID, ...)` and listens for `event.event === "message_created"`, which matches the backend.

> **Conclusion: No changes are needed to Raven's event names, payload, or room logic.**

---

## 3. Production Environment: Routing and Stability Guidelines

### 3.1 Required Invariants

**Socket.IO server:**
- Listens on host at `0.0.0.0:9001` (Frappe's `realtime/index.js` → `socketio_port`)
- **NOTE**: Later report corrected this to **port 9000** for consistency

**Public endpoint for clients:**
- `https://v2.sysmayal.cloud/socket.io/` must map to that host port, with:
  - HTTP/1.1
  - `Upgrade: websocket` and `Connection: upgrade` preserved
  - Query string preserved (`EIO=4`, `transport=...`, `sid=...`)

### 3.2 Traefik + nginx Recommendation (nginx sidecar)

**frappe-socketio container runs nginx with:**

```nginx
events { worker_connections 1024; }

http {
  upstream socketio_backend {
    server 172.17.0.1:9001;  # NOTE: Use 9000 per later correction
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

**Traefik labels for that container:**
```yaml
- "traefik.enable=true"
- "traefik.http.routers.frappe-socketio.rule=Host(`v2.sysmayal.cloud`) && PathPrefix(`/socket.io`)"
- "traefik.http.routers.frappe-socketio.entrypoints=websecure"
- "traefik.http.routers.frappe-socketio.tls.certresolver=myresolver"
- "traefik.http.services.frappe-socketio.loadbalancer.server.port=80"
```

**Ensure:**
- No other router (e.g., frappe web router) claims `/socket.io` for the same host
- There is only one Socket.IO Node process behind the port (or use `@socket.io/redis-adapter` and Traefik sticky sessions for scaling)

### 3.3 Validation Steps for Production

**From host:**
```bash
curl "http://localhost:9001/socket.io/?EIO=4&transport=polling" -iv
# → HTTP 200 with handshake JSON
# NOTE: Use port 9000 per later correction
```

**From outside:**
```bash
curl -k "https://v2.sysmayal.cloud/socket.io/?EIO=4&transport=polling" -iv
# → HTTP 200 and identical Engine.IO JSON
```

**In browser DevTools:**
- `https://v2.sysmayal.cloud/socket.io/?EIO=4&transport=polling...` returns 200
- Then WebSocket upgrade to `wss://v2.sysmayal.cloud/socket.io/?EIO=4&transport=websocket&sid=...` stays open (no immediate close)

> If all three are true, realtime transport on prod is healthy.

---

## 4. Sandbox Environment: ngrok Routing Guidelines

Sandbox is simpler: no Docker, just bench + ngrok.

**Current state:**
- Socket.IO on sandbox is listening on `localhost:9000` and responds with 200 handshake to curl
- Browser connects to `https://sysmayal.ngrok.io/socket.io/?EIO=4&transport=polling...` and gets **404 (Not Found)**
- This triggers "Realtime events are not working. Please try refreshing the page."

> **This means ngrok is not forwarding `/socket.io` to port 9000.**

### 4.1 Fix Option A: nginx as Local Multiplexer (Recommended)

Add nginx on sandbox:

```nginx
server {
  listen 8005;

  location / {
    proxy_pass http://127.0.0.1:8000;  # Frappe web
  }

  location /socket.io/ {
    proxy_pass http://127.0.0.1:9000;  # Socket.IO
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
  }
}
```

Run ngrok pointing to port 8005:
```bash
ngrok http 8005
```

Then `https://sysmayal.ngrok.io/socket.io/...` will hit port 9000 correctly, and the browser will stop getting 404s.

### 4.2 Fix Option B: Two Separate Tunnels

If separate URLs are acceptable:

**Tunnel 1: web (8000)**
```bash
ngrok http 8000
```

**Tunnel 2: socket.io (9000)**
```bash
ngrok http 9000
```

Configure Raven on sandbox to use the Socket.IO tunnel URL for realtime.

> **Option A (single URL, nginx multiplexer) is closer to prod and easier to mirror.**

### 4.3 Sandbox Validation Steps

1. `curl "http://localhost:9000/socket.io/?EIO=4&transport=polling"` → 200 (already OK)
2. `curl "https://sysmayal.ngrok.io/socket.io/?EIO=4&transport=polling"` → must be 200 after fix (currently 404)
3. `bench console` test:

```python
frappe.publish_realtime(
    "message_created",
    {
        "channel_id": channel_id,
        "sender": frappe.session.user,
        "message_id": "TEST-SANDBOX-1",
        "message_details": {"text": "Hello from sandbox console", "message_type": "Text"},
    },
    doctype="Raven Channel",
    docname=channel_id,
    after_commit=True,
)
```
→ The test message should appear in the Raven UI for that channel.

---

## 5. Raven Frontend Expectations (Both Environments)

Raven/Frappe frontend should connect like this:

```typescript
const socket = io(window.location.origin, {
  path: "/socket.io/",
  transports: ["websocket", "polling"],
  withCredentials: true,
});
```

**No hard-coded `localhost:9000` or `:9001` in the browser**; `origin + /socket.io/` should be enough if proxies are correctly configured.

If there are still transient issues, temporarily prefer WebSocket only:
```typescript
transports: ["websocket"],
```
once HTTP/WS upgrade paths are confirmed to work.

---

## 6. TL;DR for the Dev Team

1. **Do not change Raven's event logic**; the `message_created` events are correct and already centralized
2. **Prod**: ensure Traefik/nginx route `https://v2.sysmayal.cloud/socket.io/` cleanly to the Node Socket.IO server on port 9000 with HTTP/1.1 and proper upgrade headers
3. **Sandbox**: fix ngrok so `https://sysmayal.ngrok.io/socket.io/` forwards to `localhost:9000/socket.io/` (via nginx on 8005 or a dedicated tunnel)
4. Use the three validation tests (local curl, external curl, bench publish_realtime) as deployment checks for both environments

> If they follow these guidelines, Raven realtime will be stable and consistent across prod and sandbox.

---

## Corrections Applied

| Original | Corrected | Reason |
|----------|-----------|--------|
| Production port 9001 | Port 9000 | Later parallel team report confirmed 9000 is the single source of truth |

See: `/workspace/docs/PARALLEL_TEAM_MULTIPLATFORM_SPEC.md` for the updated specification.
