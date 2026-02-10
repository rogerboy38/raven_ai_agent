# Frappe/Raven Realtime Fix - Session 2 Handout

## Date: 2026-02-10

---

## Executive Summary

After extensive debugging, we discovered the **root cause** of the "Realtime events are not working" error. The issue is NOT with Nginx routing, but with **how the Raven frontend constructs Socket.IO URLs** and **how the Socket.IO server authenticates connections**.

---

## Key Finding: Port 9000 is Hardcoded in Raven

### The Problem Chain

1. **Raven's bundled JS (`index-5wEi1EGJ.js`)** constructs Socket.IO URLs using port 9000 directly
2. Browser connects to `ws://192.168.1.14:9000/socket.io/...` (bypassing any proxy)
3. The Socket.IO server at port 9000 receives the connection with **mismatched headers**:
   - `Host: localhost` (or incorrect value)
   - `Origin: undefined` (missing)
4. The authentication middleware (`authenticate.js`) rejects the connection because `host != origin`

### Debug Evidence

From `node-socketio.log`:
```
=== AUTH DEBUG === { host: 'localhost', origin: undefined, hasCookie: true }
```

This proves the headers are wrong when they reach the Socket.IO server.

---

## Architecture Understanding

### Current Setup (Sandbox)
```
┌─────────────────────────────────────────────────────────────────────┐
│                         External Access                              │
│                    (ngrok or Local IP:8005)                         │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Nginx Multiplexer (Port 8005)                    │
│   ┌─────────────────────┐    ┌────────────────────────────────┐    │
│   │  /  → Port 8013     │    │  /socket.io/ → Port 9000       │    │
│   │  (Frappe Dev Server)│    │  (Socket.IO Server)            │    │
│   └─────────────────────┘    └────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
         ┌──────────────────┐            ┌──────────────────┐
         │ Frappe Dev Server│            │ Socket.IO Server │
         │   Port 8013      │            │   Port 9000      │
         └──────────────────┘            └──────────────────┘
```

### The Problem
**Raven's frontend ignores the Nginx proxy and connects directly to port 9000!**

```
Browser loads page from: http://192.168.1.14:8005
Raven JS connects to:    ws://192.168.1.14:9000/socket.io/  ← BYPASSES NGINX!
```

---

## New Approach: Work WITH Port 9000

Instead of fighting the hardcoded port 9000, we should **fix the authentication at port 9000** to accept connections properly.

### Option A: Fix the Authentication Middleware (Recommended)

The authentication check in `~/frappe-bench/apps/frappe/realtime/middlewares/authenticate.js`:

```javascript
// Current problematic check (line ~25):
if (get_hostname(socket.request.headers.host) != get_hostname(socket.request.headers.origin)) {
    next(new Error("Invalid origin"));
    return;
}
```

**Potential fixes:**

1. **Allow same-network origins** - Modify to accept local network IPs
2. **Use X-Forwarded headers** - Check `X-Forwarded-Host` if behind proxy
3. **Configure allowed origins** - Add a whitelist in site config

### Option B: Expose Port 9000 Directly via ngrok

Instead of using Nginx multiplexer, run **two ngrok tunnels**:
- `ngrok http 8013` → For main app (e.g., `https://app.ngrok.io`)
- `ngrok http 9000` → For sockets (e.g., `https://socket.ngrok.io`)

Then configure Raven to use the socket URL.

### Option C: Modify Raven's Socket URL Construction

Find where Raven builds the Socket.IO URL and modify it to use the same origin as the page.

**Files to investigate:**
```bash
grep -r "9000\|socketio_port\|socket.io" ~/frappe-bench/apps/raven/frontend/src/
find ~/frappe-bench/apps/raven -name "*.ts" -o -name "*.tsx" | xargs grep -l "socket"
```

---

## Files Modified/Created This Session

| File | Purpose | Status |
|------|---------|--------|
| `/etc/nginx/sites-available/frappe-multiplexer` | Nginx proxy config | Created, working |
| `~/frappe-bench/apps/frappe/realtime/middlewares/authenticate.js` | Auth middleware | Debug logs added (has .bak) |
| `~/frappe-bench/sites/sysmayal2_v_frappe_cloud/site_config.json` | Site config | Modified `dev_server: 0` |

---

## Configuration Reference

### Site Config (`site_config.json`)
```json
{
  "dev_server": 1,  // Controls whether client uses separate socket port
  "socketio_port": 9000
}
```

### Common Site Config (`common_site_config.json`)
```json
{
  "socketio_port": 9000,
  "webserver_port": 8000,
  "developer_mode": 1
}
```

---

## Next Session Action Items

### Priority 1: Investigate Authentication Fix
```bash
# View the current authenticate.js
cat ~/frappe-bench/apps/frappe/realtime/middlewares/authenticate.js

# Check what headers actually arrive at Socket.IO when connecting directly
# Add more detailed logging if needed
```

### Priority 2: Find Raven's Socket Configuration
```bash
# Search Raven source for socket URL construction
grep -rn "socket" ~/frappe-bench/apps/raven/frontend/src/ | grep -i "url\|host\|port"

# Check if there's a config file
find ~/frappe-bench/apps/raven -name "*.json" -o -name "*.env*" | xargs grep -l "socket" 2>/dev/null
```

### Priority 3: Test Direct Port 9000 Access
```bash
# Test if Socket.IO works when accessed directly with correct headers
curl -v "http://localhost:9000/socket.io/?EIO=4&transport=polling" \
  -H "Host: 192.168.1.14:9000" \
  -H "Origin: http://192.168.1.14:8005"
```

---

## Questions to Answer Next Session

1. **Can we modify `authenticate.js` to be more lenient with origin checking?**
   - What are the security implications?
   - Is there a config option to whitelist origins?

2. **Where exactly does Raven construct its Socket.IO URL?**
   - Is it using Frappe's `frappe.boot.socketio_port`?
   - Or does it have its own configuration?

3. **What's the production setup going to look like?**
   - Will production also use dev_server mode?
   - How does Frappe Cloud handle Socket.IO routing?

---

## Commands Quick Reference

```bash
# Restart all services
bench restart

# Tail Socket.IO logs
tail -f ~/frappe-bench/logs/node-socketio.log

# Clear cache
bench clear-cache

# Rebuild assets (if modifying JS)
bench build

# Check running processes
bench doctor

# View site config
cat ~/frappe-bench/sites/sysmayal2_v_frappe_cloud/site_config.json
```

---

## Session Summary

We successfully traced the realtime issue from the browser → through Nginx → to the Socket.IO server. The key discovery is that **Raven bypasses our Nginx proxy entirely** and connects directly to port 9000, where the connection fails due to header validation in `authenticate.js`.

The next session should focus on **making port 9000 work correctly** rather than trying to force all traffic through port 8005.

---

*Handout prepared by Matrix Agent - 2026-02-10*
