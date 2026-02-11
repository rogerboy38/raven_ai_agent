# Socket.IO Connection Fix - Handout

## Problem Summary

The Raven web UI shows "Realtime events are not working" error because the browser connects to the wrong Socket.IO port.

### Current Behavior
- Browser connects to `ws://192.168.1.14:9000/socket.io/` (direct to socketio server)
- This bypasses the nginx multiplexer on port 8005
- Connection fails with "WebSocket closed before established"

### Expected Behavior
- Browser should connect to `ws://192.168.1.14:8005/socket.io/`
- Nginx multiplexer (port 8005) proxies `/socket.io/` to port 9000
- This is already configured correctly in `/etc/nginx/sites-enabled/frappe-multiplexer`

---

## Root Cause

Frappe injects `window.socketio_port = 9000` into the HTML page.

**Source:** `~/frappe-bench/apps/frappe/frappe/boot.py`
```python
for key in ("developer_mode", "socketio_port", "file_watcher_port"):
    if key in frappe.conf:
        bootinfo[key] = frappe.conf.get(key)
```

**Current HTML output:**
```html
window.socketio_port = 9000;
```

---

## Investigation Findings

### 1. Infrastructure is Working
```bash
# Direct to socketio - OK
curl "http://localhost:9000/socket.io/?EIO=4&transport=polling"
# Returns: 0{"sid":"...","upgrades":["websocket"],...}

# Through nginx multiplexer - OK
curl "http://localhost:8005/socket.io/?EIO=4&transport=polling"
# Returns: 0{"sid":"...","upgrades":["websocket"],...}

# Through ngrok - OK
curl "https://sysmayal.ngrok.io/socket.io/?EIO=4&transport=polling"
# Returns: 0{"sid":"...","upgrades":["websocket"],...}
```

### 2. Config Files (Current State)
**common_site_config.json:** No `socketio_port` (removed)
**site_config.json:** No `socketio_port` (removed)

### 3. The 9000 Still Appears
Despite removing `socketio_port` from configs, `window.socketio_port = 9000` still appears.

**Possible causes:**
1. Frappe has a hardcoded default of 9000 somewhere
2. Redis cache still contains old value
3. Another config location we haven't checked

---

## Attempted Solutions

| Solution | Result |
|----------|--------|
| Remove `socketio_port` from configs | Still shows 9000 |
| Set `socketio_port: 8005` | bench restart crashes (nginx already using 8005) |
| Set `developer_mode: 0` | Still shows 9000 |
| `bench clear-cache` | Still shows 9000 |

---

## Next Steps to Investigate

### 1. Check if there's a default in Frappe's JS
```bash
grep -r "9000" ~/frappe-bench/apps/frappe/frappe/public/
```

### 2. Check the actual boot info API
```bash
# Login first, then:
curl -s "http://localhost:8005/api/method/frappe.sessions.get_boot_info" -H "Cookie: sid=<your-sid>" | jq '.message.socketio_port'
```

### 3. Check Redis cache
```bash
redis-cli -p 13000 KEYS "*socket*"
```

### 4. Check if `develop.py` or `bench serve` sets defaults
```bash
grep -r "socketio_port" ~/frappe-bench/apps/frappe/frappe/utils/
```

---

## Proposed Fix Options

### Option A: Modify Frappe's JS (Not Recommended)
Edit `~/frappe-bench/apps/frappe/frappe/public/js/frappe/socketio_client.js` to not use `socketio_port` and always use `window.location.port`.

**Downside:** Frappe upgrade will overwrite.

### Option B: Override in Raven Frontend (Recommended)
If Raven has its own socket client, modify it to ignore `frappe.boot.socketio_port` and use `window.location.port` when accessing via LAN.

### Option C: Use ngrok URL Always
Access via `https://sysmayal.ngrok.io` instead of `http://192.168.1.14:8005`. The ngrok setup correctly routes socket.io.

### Option D: Find the Real Source of 9000
The fact that removing from config doesn't help means there's a default somewhere. Find and fix it.

---

## Architecture Reference

```
Browser (LAN Access)
    |
    v
http://192.168.1.14:8005
    |
    v
Nginx Multiplexer (port 8005)
    |
    +---> / (all routes) --> Frappe Web (port 8013)
    |
    +---> /socket.io/   --> Node Socket.IO (port 9000)
```

**The nginx config is correct:**
```nginx
location /socket.io/ {
    proxy_pass http://127.0.0.1:9000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    ...
}
```

---

## Related Files

| File | Purpose |
|------|---------|
| `~/frappe-bench/apps/frappe/frappe/boot.py` | Sets `socketio_port` in boot data |
| `~/frappe-bench/apps/frappe/frappe/public/js/frappe/socketio_client.js` | Frontend socket client |
| `/etc/nginx/sites-enabled/frappe-multiplexer` | Nginx proxy config |
| `~/frappe-bench/sites/common_site_config.json` | Common site config |
| `~/frappe-bench/sites/sysmayal2_v_frappe_cloud/site_config.json` | Site-specific config |

---

## Session Notes

- Python `raven_ai_agent` client fix: Uses `http://localhost:9000` in dev environment (commit `14fdfea`)
- Browser client issue: Separate from Python client, requires Frappe-level fix
- The `window.socketio_port = 9000` is injected server-side, not from site configs
