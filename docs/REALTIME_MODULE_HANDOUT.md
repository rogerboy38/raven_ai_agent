# Raven AI Agent - Realtime Module Handout

## 🚀 NEXT SESSION: START HERE

### Step 1: Tell Agent to Continue
Copy and paste this to the agent:

```
Continue from the Raven realtime module handout at docs/REALTIME_MODULE_HANDOUT.md

Current task: Fix URL scheme in realtime/client.py so Socket.IO client can connect.

The issue: python-socketio needs https:// not wss:// for initial handshake.

File to edit: /workspace/raven_ai_agent/raven_ai_agent/realtime/client.py

After fix, test on sandbox with bench console.
```

### Step 2: What Agent Should Do
1. Edit `client.py` - fix URL scheme from `wss://` to `https://`
2. Push to git
3. Test connection on sandbox

---

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

4. **Installed deps in bench env** - ✅ DONE
   ```bash
   ./env/bin/pip install "python-socketio[client]" websocket-client
   ```

---

## Current Blocker

**Connection hangs on connect()** - The client uses `wss://` scheme but python-socketio needs `https://` for initial polling handshake:

```python
# Current (wrong):
url = "wss://sysmayal.ngrok.io/socket.io"

# Should be:
url = "https://sysmayal.ngrok.io"  # python-socketio adds /socket.io automatically
```

### Error Trace
```
client = get_socketio_client(auto_connect=True)
# Hangs at: self._sio.connect(config.url, ...)
# Times out trying to connect to wss:// URL
```

---

## Fix Required

Edit `raven_ai_agent/raven_ai_agent/realtime/client.py` - Change URL scheme in `_get_config()`:

```python
def _get_config(self) -> ConnectionConfig:
    # ...
    socketio_url = get_external_socketio_url()
    
    # FIX: python-socketio needs https:// not wss://
    if socketio_url.startswith('wss://'):
        socketio_url = socketio_url.replace('wss://', 'https://')
    elif socketio_url.startswith('ws://'):
        socketio_url = socketio_url.replace('ws://', 'http://')
    
    # Also remove /socket.io suffix if present (library adds it)
    socketio_url = socketio_url.replace('/socket.io', '')
    
    return ConnectionConfig(url=socketio_url, ...)
```

---

## Testing After Fix

```python
# bench console on sandbox
import sys
sys.path.insert(0, '/home/frappe/frappe-bench/apps/raven_ai_agent/raven_ai_agent')
from realtime.client import get_socketio_client

client = get_socketio_client(auto_connect=True)
print(client.get_status())
# Should show: state: connected, is_connected: True
```

---

## Files Changed This Session

| File | Status | Location |
|------|--------|----------|
| `config/environment.py` | Updated | Detects ngrok via host_name |
| `realtime/__init__.py` | New | Module init |
| `realtime/client.py` | New | Socket.IO client (needs URL fix) |
| `pyproject.toml` | Updated | Added socketio deps |

---

## Git Status

All changes pushed to `main` branch:
- https://github.com/rogerboy38/raven_ai_agent

Latest commits:
- `7f520df` - docs: Update handout with URL scheme fix needed
- `147e3b5` - docs: Add realtime module handout
- `dc60bff` - deps: Add python-socketio and websocket-client

---

## Key Findings

1. **Frappe v16 socketio is broken** - File `frappe/socketio.py` was manually added with wrong imports. Deleted it.

2. **Environment detection works** - Config module correctly identifies:
   - Sandbox: `sandbox_ngrok` → `wss://sysmayal.ngrok.io/socket.io`
   - VPS: `traefik` → reads `socketio_port` from site_config

3. **URL scheme issue** - python-socketio library expects `https://` not `wss://`. It handles the WebSocket upgrade internally.

4. **Socket.IO server is responding** - Verified with curl:
   ```bash
   curl "https://sysmayal.ngrok.io/socket.io/?EIO=4&transport=polling"
   # Returns: 0{"sid":"xxx","upgrades":["websocket"],...}
   ```

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

## Commands Reference

```bash
# Pull latest on sandbox
cd ~/frappe-bench/apps/raven_ai_agent
git pull upstream main

# Install deps in bench env (already done)
cd ~/frappe-bench
./env/bin/pip install "python-socketio[client]" websocket-client

# Test Socket.IO server
curl "https://sysmayal.ngrok.io/socket.io/?EIO=4&transport=polling"
```

---

## Contact Points

- **Sandbox**: sysmayal.ngrok.io (ngrok tunnel)
- **VPS**: v2.sysmayal.cloud (Traefik, port 9001)
- **Repo**: github.com/rogerboy38/raven_ai_agent
