# Raven AI Agent - Realtime Module Handout

## Session Summary (2026-02-11)

### What Was Accomplished

1. **Environment-aware config module** (`raven_ai_agent/config/`) - **WORKING**
   - Correctly detects sandbox (ngrok) vs VPS (traefik) environments
   - Generates proper Socket.IO URLs based on `host_name` in site_config
   - Tested and validated on both environments

2. **Standalone Socket.IO client** (`raven_ai_agent/realtime/`) - **CREATED**
   - Bypasses broken Frappe socketio module
   - Uses config module for auto-configuration
   - Pushed to git: `raven_ai_agent/raven_ai_agent/realtime/`

3. **Dependencies added** to `pyproject.toml`:
   ```
   "python-socketio[client]>=5.0.0",
   "websocket-client>=1.0.0",
   ```

---

## Current Blocker

**python-socketio not being detected** in bench console despite being installed:

```bash
pip list | grep socketio
# Shows: python-socketio 5.16.1
```

But in bench console:
```
socketio_available: False
```

### Root Cause
The bench console runs in a different Python environment. The library is installed in user site-packages but not in the bench/frappe environment.

---

## Next Steps to Fix

### Option 1: Install in bench environment
```bash
cd ~/frappe-bench
./env/bin/pip install "python-socketio[client]" websocket-client
```

### Option 2: Install via bench
```bash
bench pip install "python-socketio[client]" websocket-client
```

### Option 3: Check Python paths
```python
# In bench console
import sys
print(sys.path)
# Then ensure the user site-packages is included
```

---

## Testing After Fix

```python
# bench console
import sys
sys.path.insert(0, '/home/frappe/frappe-bench/apps/raven_ai_agent/raven_ai_agent')
from realtime.client import get_socketio_client

client = get_socketio_client(auto_connect=True)
print(client.get_status())
# Should show: state: connected, socketio_available: True
```

---

## Files Changed This Session

| File | Status | Location |
|------|--------|----------|
| `config/environment.py` | Updated | Detects ngrok via host_name |
| `realtime/__init__.py` | New | Module init |
| `realtime/client.py` | New | Socket.IO client |
| `pyproject.toml` | Updated | Added socketio deps |

---

## Git Status

All changes pushed to `main` branch:
- https://github.com/rogerboy38/raven_ai_agent

Latest commit: `dc60bff` - deps: Add python-socketio and websocket-client

---

## Key Findings

1. **Frappe v16 socketio is broken** - File `frappe/socketio.py` was manually added with wrong imports. Deleted it.

2. **Environment detection works** - Config module correctly identifies:
   - Sandbox: `sandbox_ngrok` → `wss://sysmayal.ngrok.io/socket.io`
   - VPS: `traefik` → reads `socketio_port` from site_config

3. **Frontend issue identified** - Browser console showed `frappe.socketio: NOT FOUND`. The Raven frontend needs to use our new realtime client instead of relying on Frappe's broken one.

---

## Architecture

```
raven_ai_agent/
├── config/
│   ├── __init__.py      # Exports get_config, get_environment, etc.
│   ├── environment.py   # Environment detection logic
│   └── realtime.py      # Frappe publish helpers
└── realtime/
    ├── __init__.py      # Exports get_socketio_client, emit_event, etc.
    └── client.py        # RealtimeClient class (singleton)
```

**Usage:**
```python
from raven_ai_agent.realtime import get_socketio_client, emit_to_channel

client = get_socketio_client()
emit_to_channel('my-channel', 'message_event', {'text': 'Hello'})
```

---

## VPS Commands Reference

```bash
# Pull latest
cd ~/frappe-bench/apps/raven_ai_agent
git pull upstream main

# Install deps in bench env
cd ~/frappe-bench
./env/bin/pip install "python-socketio[client]" websocket-client
```

---

## Contact Points

- **Sandbox**: sysmayal.ngrok.io (ngrok tunnel)
- **VPS**: v2.sysmayal.cloud (Traefik, port 9001)
- **Repo**: github.com/rogerboy38/raven_ai_agent
