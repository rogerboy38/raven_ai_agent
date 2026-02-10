# Raven AI Agent - Environment Adaptive Configuration

## Overview

The `raven_ai_agent.config` module provides environment-aware configuration for the Raven AI Agent. This allows the application to automatically detect and adapt to different deployment environments:

- **Sandbox (Development)**: Local development with `bench dev`, optionally with ngrok tunnel
- **Production VPS (Traefik)**: Docker-based deployment with Traefik reverse proxy (e.g., v2.sysmayal.cloud)
- **Production (Nginx)**: Traditional Frappe deployment with Nginx + Supervisor
- **Frappe Cloud**: Managed Frappe Cloud infrastructure

## Key Files

| File | Purpose |
|------|---------|
| `config/__init__.py` | Module exports and documentation |
| `config/environment.py` | Environment detection and configuration |
| `config/realtime.py` | Environment-aware realtime publishing |
| `api/channel_utils.py` | Updated to use adaptive publishing |

## Usage

### Basic Configuration Access

```python
from raven_ai_agent.config import get_config, get_environment, is_production

# Get current environment type
env = get_environment()  # Returns DeploymentType enum

# Get full configuration
config = get_config()
print(f"Socket.IO URL: {config.get_socketio_url()}")
print(f"External URL: {config.get_external_socketio_url()}")

# Check environment
if is_production():
    print("Running in production mode")
```

### Realtime Publishing

The existing `publish_message_created_event()` function now automatically uses environment-aware configuration:

```python
from raven_ai_agent.api.channel_utils import publish_message_created_event

# This now automatically handles environment-specific settings
publish_message_created_event(message_doc, channel_id)
```

For more control, use the new realtime module directly:

```python
from raven_ai_agent.config.realtime import publish_message, diagnose_realtime

# Publish with environment awareness
publish_message(channel_id, message_data)

# Get diagnostic information
diagnosis = diagnose_realtime()
print(diagnosis)
```

### API Endpoints

New API endpoints for debugging and client configuration:

```python
# Get client-side Socket.IO configuration
GET /api/method/raven_ai_agent.api.channel_utils.get_realtime_config

# Run realtime diagnostics
GET /api/method/raven_ai_agent.api.channel_utils.diagnose_realtime_connection

# Get environment information
GET /api/method/raven_ai_agent.api.channel_utils.get_environment_info
```

## Known Environments

The module includes hardcoded configurations for known deployment environments:

### Sandbox Environment
- **Site Pattern**: `sysmayal2_v_frappe_cloud`
- **ngrok Domain**: `sysmayal.ngrok.io`
- **Socket.IO Port**: 9000
- **Web Port**: 8000
- **Multiplexer Port**: 8005 (nginx, when configured)
- **Redis Socket.IO Port**: 13000

### Production VPS (Traefik)
- **Domain**: `v2.sysmayal.cloud`
- **Socket.IO Port**: 9001 (internal), 443 (external via Traefik)
- **Uses Traefik**: Yes
- **Uses nginx Sidecar**: Yes

### Frappe Cloud
- **Domain Pattern**: `*.frappe.cloud`
- **Managed Infrastructure**: All routing handled by FC

## Environment Detection

The module uses multiple signals to detect the current environment:

1. **Environment Variables**:
   - `RAVEN_AI_DEPLOYMENT_TYPE` (override)
   - `FRAPPE_CLOUD`
   - `TRAEFIK_ENABLE`, `TRAEFIK_HOST`
   - `NGROK_URL`, `NGROK_AUTHTOKEN`
   - `SITE_DOMAIN`

2. **File System Checks**:
   - `/.dockerenv` (Docker container)
   - `/home/frappe/frappe-bench/.frappe-cloud` (Frappe Cloud)
   - `/etc/supervisor/conf.d/frappe-bench.conf` (Nginx production)

3. **Site Configuration**:
   - `developer_mode` flag
   - `frappe_cloud_site` flag
   - `traefik_host` setting
   - Site name patterns

4. **Network Detection**:
   - ngrok API check (localhost:4040)
   - Port availability checks

## Configuration Override

You can force a specific environment by setting the environment variable:

```bash
export RAVEN_AI_DEPLOYMENT_TYPE=traefik
```

Or in `site_config.json`:

```json
{
    "traefik_host": "v2.sysmayal.cloud",
    "use_traefik": true
}
```

## Troubleshooting

### Validate Connectivity

```python
from raven_ai_agent.config import validate_realtime_connectivity

validation = validate_realtime_connectivity()
print(validation["checks"])      # What's working
print(validation["warnings"])    # Potential issues
print(validation["recommendations"])  # Suggested fixes
```

### Log Diagnostics

```python
from raven_ai_agent.config.realtime import log_realtime_diagnostics

log_realtime_diagnostics()  # Logs detailed info to frappe.log
```

### Common Issues

1. **Sandbox + ngrok**: If Socket.IO fails via ngrok, ensure nginx multiplexer is running on port 8005
2. **Production VPS**: Verify Traefik routes `/socket.io` to the nginx sidecar container
3. **Frappe Cloud**: Realtime should work automatically; contact FC support if issues persist

## Integration Notes

- The existing `publish_message_created_event()` function is backward compatible
- All existing code continues to work without changes
- New functionality is opt-in via the `use_adaptive` parameter or direct module imports
- Environment detection is cached for performance (use `force_refresh=True` to bypass)

## Related Documentation

- `/workspace/docs/RAVEN_INFRASTRUCTURE_FIX_HANDOUT.md` - Infrastructure setup instructions
- `/workspace/docs/realtime-fix-handout-session2.md` - Root cause analysis
