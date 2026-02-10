"""
Environment Configuration Module for Raven AI Agent
====================================================

This module provides adaptive configuration based on the deployment environment:
- Sandbox (Development): Direct port access, bench dev server
- Production with Traefik: Docker containers, reverse proxy
- Production with Nginx: Traditional Frappe setup
- Frappe Cloud: Managed infrastructure

The app auto-detects the environment and adjusts:
1. Socket.IO connection strategy
2. Real-time event publishing
3. Redis connection settings
4. File paths and URLs
"""

import os
import socket
import frappe
from typing import Dict, Optional, Any
from enum import Enum
from dataclasses import dataclass


class DeploymentType(Enum):
    """Supported deployment environments"""
    SANDBOX = "sandbox"              # Development with bench
    PRODUCTION_TRAEFIK = "traefik"   # Docker + Traefik reverse proxy
    PRODUCTION_NGINX = "nginx"       # Traditional Nginx + Supervisor
    FRAPPE_CLOUD = "frappe_cloud"    # Managed Frappe Cloud
    UNKNOWN = "unknown"


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
        except:
            pass
        
        return False
    
    def _is_docker_traefik(self) -> bool:
        """Check if running in Docker with Traefik"""
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
        except:
            pass
        
        # Check for typical development paths
        bench_path = os.environ.get("FRAPPE_BENCH_ROOT", "/home/frappe/frappe-bench")
        if os.path.exists(os.path.join(bench_path, "Procfile")):
            # Procfile exists - likely development
            return True
        
        return False
    
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
        socketio_port = site_config.get("socketio_port") or common_config.get("socketio_port", 9000)
        redis_socketio = common_config.get("redis_socketio", "redis://localhost:13000")
        
        # In sandbox, we often access via local IP or ngrok
        site_name = getattr(frappe.local, 'site', 'localhost')
        
        return EnvironmentConfig(
            deployment_type=DeploymentType.SANDBOX,
            socketio_port=socketio_port,
            socketio_host="localhost",
            redis_socketio=redis_socketio,
            use_ssl=False,
            site_url=f"http://{site_name}",
            websocket_path="/socket.io",
            proxy_headers_required=False,
            realtime_strategy="frappe_native",
            debug_mode=True,
            cors_origins=["*"]  # Allow all in development
        )
    
    def _get_traefik_config(self, site_config: Dict, common_config: Dict) -> EnvironmentConfig:
        """Configuration for Docker + Traefik deployment"""
        # In Traefik setup, Socket.IO is typically on same port via path routing
        socketio_port = 443  # HTTPS via Traefik
        redis_socketio = common_config.get("redis_socketio", "redis://redis-socketio:6379")
        
        site_name = getattr(frappe.local, 'site', os.environ.get("SITE_NAME", "localhost"))
        traefik_host = site_config.get("traefik_host") or os.environ.get("TRAEFIK_HOST", site_name)
        
        return EnvironmentConfig(
            deployment_type=DeploymentType.PRODUCTION_TRAEFIK,
            socketio_port=socketio_port,
            socketio_host=traefik_host,
            redis_socketio=redis_socketio,
            use_ssl=True,
            site_url=f"https://{traefik_host}",
            websocket_path="/socket.io",
            proxy_headers_required=True,
            realtime_strategy="frappe_native",
            debug_mode=False,
            cors_origins=[f"https://{traefik_host}"]
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
    protocol = "wss" if config.use_ssl else "ws"
    
    if config.socketio_port in [80, 443]:
        return f"{protocol}://{config.socketio_host}{config.websocket_path}"
    else:
        return f"{protocol}://{config.socketio_host}:{config.socketio_port}{config.websocket_path}"


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


# Export commonly used functions
__all__ = [
    'DeploymentType',
    'EnvironmentConfig',
    'EnvironmentDetector',
    'get_environment',
    'get_config',
    'get_socketio_url',
    'get_allowed_origins',
    'is_production',
    'is_development',
    'log_environment_info'
]
