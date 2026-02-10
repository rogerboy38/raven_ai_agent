"""
Environment Configuration Module for Raven AI Agent
====================================================

This module provides adaptive configuration based on the deployment environment:
- Sandbox (Development): Direct port access, bench dev server, ngrok tunnel
- Production with Traefik: Docker containers on VPS (e.g., v2.sysmayal.cloud)
- Production with Nginx: Traditional Frappe setup
- Frappe Cloud: Managed infrastructure (e.g., *.frappe.cloud sites)

The app auto-detects the environment and adjusts:
1. Socket.IO connection strategy (port 9000 for sandbox, 9001 for prod)
2. Real-time event publishing
3. Redis connection settings
4. File paths and URLs
5. CORS and authentication handling

Known Environments:
- Sandbox: ngrok tunnel -> nginx multiplexer (8005) -> 8000/9000
- Production VPS: Traefik -> nginx sidecar -> Socket.IO on 9001
- Frappe Cloud: Managed infrastructure
"""

import os
import socket
import frappe
from typing import Dict, Optional, Any
from enum import Enum
from dataclasses import dataclass


class DeploymentType(Enum):
    """Supported deployment environments"""
    SANDBOX = "sandbox"              # Development with bench, ngrok tunnel
    SANDBOX_NGROK = "sandbox_ngrok"  # Sandbox specifically with ngrok
    PRODUCTION_TRAEFIK = "traefik"   # Docker + Traefik reverse proxy (VPS)
    PRODUCTION_NGINX = "nginx"       # Traditional Nginx + Supervisor
    FRAPPE_CLOUD = "frappe_cloud"    # Managed Frappe Cloud
    UNKNOWN = "unknown"


# Known environment configurations from infrastructure documentation
# NOTE: socketio_port is READ FROM SITE CONFIG at runtime, not hardcoded here.
# VPS uses 9001, sandbox uses 9000 - these are their actual configurations.
KNOWN_ENVIRONMENTS = {
    # Sandbox environment details
    "sandbox": {
        "site_pattern": "sysmayal2_v_frappe_cloud",  # Site name pattern
        "ngrok_domain": "sysmayal.ngrok.io",
        "default_socketio_port": 9000,  # Fallback only
        "web_port": 8000,
        "multiplexer_port": 8005,  # nginx multiplexer when properly configured
        "redis_socketio_port": 13000,
    },
    # Production VPS with Traefik
    "production_vps": {
        "domain": "v2.sysmayal.cloud",
        "default_socketio_port": 9001,  # VPS uses 9001 per actual site config
        "uses_traefik": True,
        "uses_nginx_sidecar": True,
        # External access via Traefik on 443, routes to nginx sidecar
    },
    # Frappe Cloud
    "frappe_cloud": {
        "domain_pattern": ".frappe.cloud",
        "managed": True,
    }
}


@dataclass
class EnvironmentConfig:
    """Environment-specific configuration"""
    deployment_type: DeploymentType
    socketio_port: int
    socketio_host: str
    redis_socketio: str
    use_ssl: bool
    site_url: str
    websocket_path: str
    proxy_headers_required: bool
    
    # Real-time publishing strategy
    realtime_strategy: str  # "direct", "redis_pubsub", "frappe_native"
    
    # Additional settings
    debug_mode: bool
    cors_origins: list
    
    # Environment-specific extras
    ngrok_tunnel: Optional[str] = None  # ngrok URL if applicable
    traefik_host: Optional[str] = None  # Traefik routing host
    is_multiplexer_enabled: bool = False  # Whether nginx multiplexer is active
    
    def get_socketio_url(self) -> str:
        """Get the full Socket.IO URL for this environment."""
        protocol = "wss" if self.use_ssl else "ws"
        
        # If ngrok tunnel is available and we're in sandbox, use it
        if self.ngrok_tunnel and self.deployment_type in [DeploymentType.SANDBOX, DeploymentType.SANDBOX_NGROK]:
            return f"wss://{self.ngrok_tunnel}/socket.io"
        
        if self.socketio_port in [80, 443]:
            return f"{protocol}://{self.socketio_host}{self.websocket_path}"
        else:
            return f"{protocol}://{self.socketio_host}:{self.socketio_port}{self.websocket_path}"
    
    def get_external_socketio_url(self) -> str:
        """
        Get the Socket.IO URL that external clients (browser) should use.
        This handles the ngrok/traefik indirection.
        """
        if self.ngrok_tunnel:
            return f"wss://{self.ngrok_tunnel}/socket.io"
        elif self.traefik_host:
            return f"wss://{self.traefik_host}/socket.io"
        else:
            return self.get_socketio_url()


class EnvironmentDetector:
    """
    Detects the current deployment environment and provides
    appropriate configuration.
    """
    
    _instance = None
    _config_cache: Optional[EnvironmentConfig] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def detect_environment(self) -> DeploymentType:
        """
        Auto-detect the deployment environment based on various signals.
        """
        # Check environment variable override first
        env_override = os.environ.get("RAVEN_AI_DEPLOYMENT_TYPE")
        if env_override:
            try:
                return DeploymentType(env_override.lower())
            except ValueError:
                pass
        
        # Check for Frappe Cloud
        if self._is_frappe_cloud():
            return DeploymentType.FRAPPE_CLOUD
        
        # Check for Docker/Traefik
        if self._is_docker_traefik():
            return DeploymentType.PRODUCTION_TRAEFIK
        
        # Check for traditional Nginx production
        if self._is_nginx_production():
            return DeploymentType.PRODUCTION_NGINX
        
        # Check for development/sandbox
        if self._is_sandbox():
            return DeploymentType.SANDBOX
        
        return DeploymentType.UNKNOWN
    
    def _is_frappe_cloud(self) -> bool:
        """Check if running on Frappe Cloud"""
        # Frappe Cloud sets specific environment variables
        if os.environ.get("FRAPPE_CLOUD"):
            return True
        
        # Check for Frappe Cloud specific paths
        if os.path.exists("/home/frappe/frappe-bench/.frappe-cloud"):
            return True
        
        # Check site config for Frappe Cloud markers
        try:
            site_config = frappe.get_site_config()
            if site_config.get("frappe_cloud_site"):
                return True
            
            # Check if site name matches Frappe Cloud pattern
            site_name = getattr(frappe.local, 'site', '')
            if site_name and '.frappe.cloud' in site_name:
                return True
        except:
            pass
        
        return False
    
    def _is_docker_traefik(self) -> bool:
        """Check if running in Docker with Traefik or VPS production"""
        # Check for known production domain (v2.sysmayal.cloud) via host_name
        try:
            site_config = frappe.get_site_config()
            host_name = site_config.get("host_name", "")
            if "v2.sysmayal.cloud" in host_name:
                return True
            
            # Check domains list
            domains = site_config.get("domains", [])
            if any("v2.sysmayal.cloud" in d for d in domains):
                return True
        except:
            pass
        
        # Check for Docker-specific paths
        if os.path.exists("/.dockerenv"):
            # Check for Traefik labels or environment
            if os.environ.get("TRAEFIK_ENABLE") or os.environ.get("TRAEFIK_HOST"):
                return True
            
            # Check for common Traefik network names
            try:
                hostname = socket.gethostname()
                if "traefik" in hostname.lower() or "docker" in hostname.lower():
                    return True
            except:
                pass
            
            # Check site config for Traefik markers
            try:
                site_config = frappe.get_site_config()
                if site_config.get("use_traefik") or site_config.get("traefik_host"):
                    return True
            except:
                pass
        
        # Check for known production domain (v2.sysmayal.cloud)
        try:
            site_name = getattr(frappe.local, 'site', '')
            if site_name and 'v2.sysmayal.cloud' in site_name:
                return True
            
            # Check environment variable for domain
            site_domain = os.environ.get("SITE_DOMAIN", "")
            if 'v2.sysmayal.cloud' in site_domain:
                return True
        except:
            pass
        
        return False
    
    def _is_nginx_production(self) -> bool:
        """Check if running with traditional Nginx production setup"""
        # Check for supervisor
        if os.path.exists("/etc/supervisor/conf.d/frappe-bench.conf"):
            return True
        
        # Check for systemd Frappe services
        if os.path.exists("/etc/systemd/system/frappe-bench-web.service"):
            return True
        
        # Check site config for production markers
        try:
            site_config = frappe.get_site_config()
            if site_config.get("developer_mode") == 0:
                # Not developer mode = production
                common_config = frappe.get_conf()
                if not common_config.get("developer_mode"):
                    return True
        except:
            pass
        
        return False
    
    def _is_sandbox(self) -> bool:
        """Check if running in development/sandbox mode"""
        # Check for bench command
        try:
            site_config = frappe.get_site_config()
            common_config = frappe.get_conf()
            
            if site_config.get("developer_mode") or common_config.get("developer_mode"):
                return True
            
            if site_config.get("dev_server"):
                return True
            
            # Check for known sandbox site pattern
            site_name = getattr(frappe.local, 'site', '')
            if site_name and 'sysmayal2_v_frappe_cloud' in site_name:
                return True
        except:
            pass
        
        # Check for typical development paths
        bench_path = os.environ.get("FRAPPE_BENCH_ROOT", "/home/frappe/frappe-bench")
        if os.path.exists(os.path.join(bench_path, "Procfile")):
            # Procfile exists - likely development
            return True
        
        # Check for ngrok process or environment hints
        if os.environ.get("NGROK_URL") or os.environ.get("NGROK_AUTHTOKEN"):
            return True
        
        return False
    
    def _detect_ngrok_tunnel(self) -> Optional[str]:
        """
        Detect if ngrok tunnel is active and return the tunnel URL.
        """
        # Check environment variable first
        ngrok_url = os.environ.get("NGROK_URL")
        if ngrok_url:
            return ngrok_url.replace("https://", "").replace("http://", "")
        
        # Check site config for ngrok URL (could be in host_name, ngrok_url, or ngrok_tunnel)
        try:
            site_config = frappe.get_site_config()
            host_name = site_config.get("host_name", "")
            # If host_name contains ngrok, use it
            if host_name and "ngrok" in host_name:
                return host_name.replace("https://", "").replace("http://", "")
            ngrok_url = site_config.get("ngrok_url") or site_config.get("ngrok_tunnel")
            if ngrok_url:
                return ngrok_url.replace("https://", "").replace("http://", "")
        except:
            pass
        
        # Try to detect ngrok via API (if ngrok is running locally)
        try:
            import urllib.request
            import json
            response = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1)
            data = json.loads(response.read())
            for tunnel in data.get("tunnels", []):
                if tunnel.get("proto") == "https":
                    public_url = tunnel.get("public_url", "")
                    return public_url.replace("https://", "")
        except:
            pass
        
        # Return known sandbox ngrok domain if site matches
        try:
            site_name = getattr(frappe.local, 'site', '')
            if 'sysmayal2_v_frappe_cloud' in site_name:
                return KNOWN_ENVIRONMENTS["sandbox"]["ngrok_domain"]
        except:
            pass
        
        return None
    
    def get_config(self, force_refresh: bool = False) -> EnvironmentConfig:
        """
        Get the environment configuration, with caching.
        """
        if self._config_cache and not force_refresh:
            return self._config_cache
        
        deployment_type = self.detect_environment()
        
        # Get base configuration from site
        try:
            site_config = frappe.get_site_config()
            common_config = frappe.get_conf()
        except:
            site_config = {}
            common_config = {}
        
        # Build configuration based on deployment type
        if deployment_type == DeploymentType.SANDBOX:
            config = self._get_sandbox_config(site_config, common_config)
        elif deployment_type == DeploymentType.PRODUCTION_TRAEFIK:
            config = self._get_traefik_config(site_config, common_config)
        elif deployment_type == DeploymentType.PRODUCTION_NGINX:
            config = self._get_nginx_config(site_config, common_config)
        elif deployment_type == DeploymentType.FRAPPE_CLOUD:
            config = self._get_frappe_cloud_config(site_config, common_config)
        else:
            config = self._get_fallback_config(site_config, common_config)
        
        self._config_cache = config
        return config
    
    def _get_sandbox_config(self, site_config: Dict, common_config: Dict) -> EnvironmentConfig:
        """Configuration for sandbox/development environment"""
        # Use known sandbox configuration
        sandbox_env = KNOWN_ENVIRONMENTS["sandbox"]
        socketio_port = site_config.get("socketio_port") or common_config.get("socketio_port", sandbox_env["socketio_port"])
        redis_socketio = common_config.get("redis_socketio", f"redis://localhost:{sandbox_env['redis_socketio_port']}")
        
        # In sandbox, we often access via local IP or ngrok
        site_name = getattr(frappe.local, 'site', 'localhost')
        
        # Detect ngrok tunnel
        ngrok_tunnel = self._detect_ngrok_tunnel()
        
        # Determine SSL based on ngrok presence
        use_ssl = ngrok_tunnel is not None
        
        # Check if nginx multiplexer is configured (port 8005)
        is_multiplexer_enabled = self._check_multiplexer_enabled(sandbox_env["multiplexer_port"])
        
        return EnvironmentConfig(
            deployment_type=DeploymentType.SANDBOX_NGROK if ngrok_tunnel else DeploymentType.SANDBOX,
            socketio_port=socketio_port,
            socketio_host="localhost",
            redis_socketio=redis_socketio,
            use_ssl=use_ssl,
            site_url=f"https://{ngrok_tunnel}" if ngrok_tunnel else f"http://{site_name}",
            websocket_path="/socket.io",
            proxy_headers_required=ngrok_tunnel is not None,
            realtime_strategy="frappe_native",
            debug_mode=True,
            cors_origins=["*", f"https://{ngrok_tunnel}"] if ngrok_tunnel else ["*"],
            ngrok_tunnel=ngrok_tunnel,
            is_multiplexer_enabled=is_multiplexer_enabled
        )
    
    def _check_multiplexer_enabled(self, port: int) -> bool:
        """Check if nginx multiplexer is running on specified port."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            return result == 0
        except:
            return False
    
    def _get_traefik_config(self, site_config: Dict, common_config: Dict) -> EnvironmentConfig:
        """Configuration for Docker + Traefik deployment (e.g., v2.sysmayal.cloud)"""
        # Read socketio_port from site config (VPS uses 9001)
        internal_socketio_port = site_config.get("socketio_port") or common_config.get("socketio_port", 9001)
        
        # External connection goes through Traefik on 443
        external_socketio_port = 443  # HTTPS via Traefik
        
        redis_socketio = common_config.get("redis_socketio", "redis://redis-socketio:6379")
        
        site_name = getattr(frappe.local, 'site', os.environ.get("SITE_NAME", "localhost"))
        
        # Get domain from host_name or domains list
        host_name = site_config.get("host_name", "").replace("https://", "").replace("http://", "")
        domains = site_config.get("domains", [])
        traefik_host = host_name or (domains[0] if domains else KNOWN_ENVIRONMENTS["production_vps"]["domain"])
        
        return EnvironmentConfig(
            deployment_type=DeploymentType.PRODUCTION_TRAEFIK,
            socketio_port=external_socketio_port,  # External clients connect via 443
            socketio_host=traefik_host,
            redis_socketio=redis_socketio,
            use_ssl=True,
            site_url=f"https://{traefik_host}",
            websocket_path="/socket.io",
            proxy_headers_required=True,
            realtime_strategy="frappe_native",
            debug_mode=False,
            cors_origins=[f"https://{traefik_host}"],
            traefik_host=traefik_host
        )
    
    def _get_nginx_config(self, site_config: Dict, common_config: Dict) -> EnvironmentConfig:
        """Configuration for traditional Nginx + Supervisor deployment"""
        socketio_port = site_config.get("socketio_port") or common_config.get("socketio_port", 9000)
        redis_socketio = common_config.get("redis_socketio", "redis://localhost:11000")
        
        site_name = getattr(frappe.local, 'site', 'localhost')
        
        return EnvironmentConfig(
            deployment_type=DeploymentType.PRODUCTION_NGINX,
            socketio_port=socketio_port,
            socketio_host=site_name,
            redis_socketio=redis_socketio,
            use_ssl=True,  # Assume production uses SSL
            site_url=f"https://{site_name}",
            websocket_path="/socket.io",
            proxy_headers_required=True,
            realtime_strategy="frappe_native",
            debug_mode=False,
            cors_origins=[f"https://{site_name}"]
        )
    
    def _get_frappe_cloud_config(self, site_config: Dict, common_config: Dict) -> EnvironmentConfig:
        """Configuration for Frappe Cloud managed environment"""
        # Frappe Cloud handles all the infrastructure
        site_name = getattr(frappe.local, 'site', 'localhost')
        
        return EnvironmentConfig(
            deployment_type=DeploymentType.FRAPPE_CLOUD,
            socketio_port=443,
            socketio_host=site_name,
            redis_socketio="managed",  # Frappe Cloud manages this
            use_ssl=True,
            site_url=f"https://{site_name}",
            websocket_path="/socket.io",
            proxy_headers_required=False,  # FC handles headers
            realtime_strategy="frappe_native",
            debug_mode=False,
            cors_origins=[f"https://{site_name}"]
        )
    
    def _get_fallback_config(self, site_config: Dict, common_config: Dict) -> EnvironmentConfig:
        """Fallback configuration when environment is unknown"""
        socketio_port = site_config.get("socketio_port") or common_config.get("socketio_port", 9000)
        redis_socketio = common_config.get("redis_socketio", "redis://localhost:11000")
        site_name = getattr(frappe.local, 'site', 'localhost')
        
        return EnvironmentConfig(
            deployment_type=DeploymentType.UNKNOWN,
            socketio_port=socketio_port,
            socketio_host="localhost",
            redis_socketio=redis_socketio,
            use_ssl=False,
            site_url=f"http://{site_name}",
            websocket_path="/socket.io",
            proxy_headers_required=False,
            realtime_strategy="frappe_native",
            debug_mode=True,
            cors_origins=["*"]
        )


# Global instance for easy access
_detector = EnvironmentDetector()


def get_environment() -> DeploymentType:
    """Get the current deployment environment type."""
    return _detector.detect_environment()


def get_config() -> EnvironmentConfig:
    """Get the current environment configuration."""
    return _detector.get_config()


def get_socketio_url() -> str:
    """
    Get the full Socket.IO URL for the current environment.
    This is useful for client-side configuration.
    """
    config = get_config()
    return config.get_socketio_url()


def get_external_socketio_url() -> str:
    """
    Get the Socket.IO URL that external clients (browser) should use.
    This handles ngrok/traefik indirection automatically.
    """
    config = get_config()
    return config.get_external_socketio_url()


def get_allowed_origins() -> list:
    """Get the list of allowed CORS origins for the current environment."""
    config = get_config()
    return config.cors_origins


def is_production() -> bool:
    """Check if running in a production environment."""
    env = get_environment()
    return env in [
        DeploymentType.PRODUCTION_NGINX,
        DeploymentType.PRODUCTION_TRAEFIK,
        DeploymentType.FRAPPE_CLOUD
    ]


def is_development() -> bool:
    """Check if running in a development environment."""
    env = get_environment()
    return env == DeploymentType.SANDBOX


def log_environment_info():
    """Log the detected environment information (for debugging)."""
    config = get_config()
    frappe.logger().info(f"[Raven AI Agent] Environment Detection:")
    frappe.logger().info(f"  Deployment Type: {config.deployment_type.value}")
    frappe.logger().info(f"  Socket.IO Host: {config.socketio_host}:{config.socketio_port}")
    frappe.logger().info(f"  SSL: {config.use_ssl}")
    frappe.logger().info(f"  Real-time Strategy: {config.realtime_strategy}")
    frappe.logger().info(f"  Debug Mode: {config.debug_mode}")


def get_environment_summary() -> Dict[str, Any]:
    """
    Get a summary of the current environment for debugging/logging.
    """
    config = get_config()
    return {
        "deployment_type": config.deployment_type.value,
        "socketio_url": config.get_socketio_url(),
        "external_socketio_url": config.get_external_socketio_url(),
        "use_ssl": config.use_ssl,
        "debug_mode": config.debug_mode,
        "ngrok_tunnel": config.ngrok_tunnel,
        "traefik_host": config.traefik_host,
        "is_multiplexer_enabled": config.is_multiplexer_enabled,
        "realtime_strategy": config.realtime_strategy,
    }


def validate_realtime_connectivity() -> Dict[str, Any]:
    """
    Validate that realtime connectivity is properly configured.
    Returns a dict with validation results and recommendations.
    """
    config = get_config()
    results = {
        "environment": config.deployment_type.value,
        "checks": [],
        "warnings": [],
        "recommendations": []
    }
    
    # Check based on environment type
    if config.deployment_type in [DeploymentType.SANDBOX, DeploymentType.SANDBOX_NGROK]:
        # Sandbox checks
        if config.ngrok_tunnel:
            results["checks"].append(f"✓ ngrok tunnel detected: {config.ngrok_tunnel}")
            if not config.is_multiplexer_enabled:
                results["warnings"].append("⚠ nginx multiplexer not detected on port 8005")
                results["recommendations"].append(
                    "For proper Socket.IO routing via ngrok, configure nginx multiplexer on port 8005. "
                    "See RAVEN_INFRASTRUCTURE_FIX_HANDOUT.md for setup instructions."
                )
        else:
            results["checks"].append("✓ Local development mode (no ngrok)")
            results["recommendations"].append(
                "Socket.IO available at localhost:9000. For external access, configure ngrok."
            )
    
    elif config.deployment_type == DeploymentType.PRODUCTION_TRAEFIK:
        results["checks"].append(f"✓ Traefik production detected: {config.traefik_host}")
        results["recommendations"].append(
            "Ensure Traefik is configured to route /socket.io to the nginx sidecar container."
        )
    
    elif config.deployment_type == DeploymentType.FRAPPE_CLOUD:
        results["checks"].append("✓ Frappe Cloud detected (managed infrastructure)")
        results["recommendations"].append(
            "Realtime is managed by Frappe Cloud. No additional configuration needed."
        )
    
    return results


# Export commonly used functions
__all__ = [
    'DeploymentType',
    'EnvironmentConfig',
    'EnvironmentDetector',
    'KNOWN_ENVIRONMENTS',
    'get_environment',
    'get_config',
    'get_socketio_url',
    'get_external_socketio_url',
    'get_allowed_origins',
    'is_production',
    'is_development',
    'log_environment_info',
    'get_environment_summary',
    'validate_realtime_connectivity'
]
