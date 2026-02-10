# Multi-Platform Configuration Specification
## Report from Parallel Team - 2026-02-10

> **Source**: Parallel team analysis
> **Purpose**: Align raven_ai_agent configuration across VPS, Sandbox, and Local environments

---

## 1. High-Level Goal

Design `raven_ai_agent` so that the **same Python code**:

```python
from raven_ai_agent.api.channel_utils import publish_message_created_event
publish_message_created_event(message_doc, channel_id)
```

works unchanged across:

| Environment | External Domain | Notes |
|-------------|-----------------|-------|
| VPS Production | `v2.sysmayal.cloud` | Traefik + nginx |
| Sandbox | `sysmayal.ngrok.io` | bench on Ubuntu + ngrok |
| Local Dev | `localhost:8000` | plain `bench start` or `bench start --dev` |

Environment-specific details (ports, domains, HTTPS vs HTTP) must live in a small config module:

```python
from raven_ai_agent.config import get_config, diagnose_realtime

config = get_config()
print(config.deployment_type.value)
print(config.get_external_socketio_url())

diagnosis = diagnose_realtime()
print(diagnosis)
```

---

## 2. Key Finding: Port 9000 is the Correct Socket.IO Port

**CRITICAL**: Use `socketio_port = 9000` as the **single source of truth** on Frappe side for both VPS and sandbox.

- Node `apps/frappe/realtime/index.js` listens on socketio_port and logs: `Realtime service listening on: ws://0.0.0.0:9000`
- Both `common_site_config.json` and `site_config.json` should have `"socketio_port": 9000`
- **Remove any old references to port 9001** in scripts (start_v3.sh or Docker labels)

---

## 3. Configuration Model Recommendation

The parallel team suggests this simplified model:

```python
# raven_ai_agent/config.py
from enum import Enum
import frappe

class DeploymentType(str, Enum):
    VPS_PROD = "vps_prod"
    SANDBOX = "sandbox"
    LOCAL = "local"

class RavenConfig:
    def __init__(self, deployment_type: DeploymentType, base_url: str, socketio_port: int):
        self.deployment_type = deployment_type
        self.base_url = base_url.rstrip("/")
        self.socketio_port = socketio_port

    def get_external_http_base(self) -> str:
        return self.base_url

    def get_external_socketio_url(self) -> str:
        """
        Return the full Socket.IO base URL that the frontend should use,
        e.g. https://v2.sysmayal.cloud or https://sysmayal.ngrok.io
        """
        # For prod and sandbox, we use the same origin as Frappe,
        # and rely on proxies/ngrok to route /socket.io/ correctly.
        return self.base_url

def get_config() -> RavenConfig:
    conf = frappe.get_conf()
    site_conf = frappe.local.conf

    host_name = site_conf.get("host_name")
    web_port = int(site_conf.get("webserver_port", conf.get("webserver_port", 8000)))
    socketio_port = int(site_conf.get("socketio_port", conf.get("socketio_port", 9000)))

    # Infer deployment type
    if host_name == "v2.sysmayal.cloud":
        deployment = DeploymentType.VPS_PROD
        base_url = f"https://{host_name}"
    elif host_name and "ngrok.io" in host_name:
        deployment = DeploymentType.SANDBOX
        base_url = f"https://{host_name}"
    else:
        deployment = DeploymentType.LOCAL
        base_url = f"http://localhost:{web_port}"

    return RavenConfig(
        deployment_type=deployment,
        base_url=base_url,
        socketio_port=socketio_port,
    )
```

---

## 4. Frontend Contract

**The contract for frontend is:**

For all deployments, connect to Socket.IO on the **same origin as the Frappe site**, with path: `"/socket.io/"`.

```typescript
const socket = io(config.socketio_base_url, {
  path: config.socketio_path,
  transports: ["websocket", "polling"],
  withCredentials: true,
});
```

**No hard-coded `:9000` in the browser**; use origin + `/socket.io/` and rely on infra to route correctly.

---

## 5. VPS Production Requirements

Given what was discovered on the VPS:

### Frappe Config
```json
{
  "socketio_port": 9000,
  "webserver_port": 8000
}
```

### Infrastructure Requirements

1. **Single public endpoint**: `https://v2.sysmayal.cloud/socket.io/` → forwards to `http://<Frappe-host>:9000/socket.io/`

2. **Traefik + nginx rules** (with port 9000):

```nginx
# nginx inside frappe-socketio container
upstream socketio_backend { server 172.17.0.1:9000; }

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
```

3. **Traefik labels**:
```yaml
- "traefik.http.routers.frappe-socketio.rule=Host(`v2.sysmayal.cloud`) && PathPrefix(`/socket.io`)"
- "traefik.http.services.frappe-socketio.loadbalancer.server.port=80"
```

---

## 6. Sandbox Requirements

From sandbox analysis:
- `socketio_port` is 9000 in both `common_site_config.json` and `site_config.json`
- Frappe web is on 8000
- **Current issue**: Browser hits `https://sysmayal.ngrok.io/socket.io/...` and gets 404 because ngrok only forwards to 8000

### Solution

Update ngrok (or nginx in front) so that:
- `/` → `localhost:8000` (Frappe web)
- `/socket.io/` → `localhost:9000` (Socket.IO server)

Once done:
- `config.get_external_socketio_url()` returns `https://sysmayal.ngrok.io`
- FE connects to `https://sysmayal.ngrok.io/socket.io/`
- Internally reaches port 9000

---

## 7. Diagnostics Helper

The `diagnose_realtime()` function should:

1. Print `deployment_type` and `socketio_port`
2. Try local check: `curl` equivalent to `http://localhost:<socketio_port>/socket.io/?EIO=4&transport=polling`
3. Try external check: `requests.get(config.get_external_socketio_url() + "/socket.io/?EIO=4&transport=polling")`

Return structured result:
```python
{
  "deployment_type": "sandbox",
  "local_socketio_ok": True,
  "external_socketio_ok": False,
  "hint": "External /socket.io/ is not mapped to socketio_port 9000"
}
```

---

## 8. Key Takeaways for Dev Team

1. **Use `socketio_port = 9000`** as the single source of truth on Frappe side for both VPS and sandbox
2. **Map host names → deployment type → base URL** in `raven_ai_agent.config`
3. **Ensure infra maps `<base_url>/socket.io/`** to socketio_port (9000) in every environment
4. **Raven app code should keep using** `publish_message_created_event(message_doc, channel_id)` and never hard-code ports or paths

With these pieces, the "multi-platform environment adapter" becomes just configuration and routing; the Raven code path stays identical across VPS, sandbox, and local.

---

## Status

- [x] Configuration module implemented (`raven_ai_agent/config/environment.py`)
- [x] Realtime helper implemented (`raven_ai_agent/config/realtime.py`)
- [x] API endpoints added to `channel_utils.py`
- [x] **UPDATED**: KNOWN_ENVIRONMENTS now uses port 9000 consistently for both sandbox AND production
- [ ] **Pending**: Infrastructure fix on VPS (nginx sidecar pointing to 9000)
- [ ] **Pending**: Infrastructure fix on Sandbox (ngrok/nginx multiplexer for `/socket.io/`)
