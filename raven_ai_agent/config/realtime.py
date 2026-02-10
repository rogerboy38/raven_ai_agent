"""
Adaptive Realtime Helper for Raven AI Agent
============================================

This module provides environment-aware realtime event publishing.
It wraps frappe.publish_realtime with environment-specific handling
to ensure reliable message delivery across different deployment scenarios.

Usage:
    from raven_ai_agent.config.realtime import publish_message, validate_connection
    
    # Publish a message (environment-aware)
    publish_message(channel_id, message_data)
    
    # Validate realtime connectivity
    status = validate_connection()
"""

import frappe
from typing import Dict, Any, Optional
from .environment import (
    get_config,
    get_environment,
    DeploymentType,
    is_production,
    log_environment_info,
    validate_realtime_connectivity,
)


def publish_message(
    channel_id: str,
    message_data: Dict[str, Any],
    event_name: str = "message_created",
    after_commit: bool = True,
    log_debug: bool = True
) -> bool:
    """
    Publish a realtime message with environment-aware handling.
    
    This function wraps frappe.publish_realtime with additional
    environment-specific logic for reliable delivery.
    
    Args:
        channel_id: The Raven Channel ID (docname)
        message_data: The message payload
        event_name: The realtime event name (default: "message_created")
        after_commit: Whether to publish after DB commit (default: True)
        log_debug: Whether to log debug information (default: True)
    
    Returns:
        bool: True if publish was successful
    """
    config = get_config()
    
    if log_debug and config.debug_mode:
        frappe.logger().debug(f"[Raven AI Agent] Publishing to channel {channel_id}")
        frappe.logger().debug(f"[Raven AI Agent] Environment: {config.deployment_type.value}")
        frappe.logger().debug(f"[Raven AI Agent] Socket.IO URL: {config.get_external_socketio_url()}")
    
    try:
        # Use the standard frappe.publish_realtime
        # The environment configuration affects the client-side connection,
        # not the server-side publish call
        frappe.publish_realtime(
            event_name,
            message_data,
            doctype="Raven Channel",
            docname=channel_id,
            after_commit=after_commit,
        )
        
        if log_debug and config.debug_mode:
            frappe.logger().debug(f"[Raven AI Agent] Successfully published {event_name} to {channel_id}")
        
        return True
        
    except Exception as e:
        frappe.logger().error(f"[Raven AI Agent] Failed to publish realtime event: {e}")
        
        # Log environment info for debugging
        if config.debug_mode:
            log_environment_info()
            validation = validate_realtime_connectivity()
            if validation["warnings"]:
                for warning in validation["warnings"]:
                    frappe.logger().warning(f"[Raven AI Agent] {warning}")
            if validation["recommendations"]:
                for rec in validation["recommendations"]:
                    frappe.logger().info(f"[Raven AI Agent] Recommendation: {rec}")
        
        return False


def publish_message_batch(
    messages: list,
    event_name: str = "message_created",
    after_commit: bool = True
) -> Dict[str, bool]:
    """
    Publish multiple messages at once.
    
    Args:
        messages: List of dicts with 'channel_id' and 'message_data' keys
        event_name: The realtime event name
        after_commit: Whether to publish after DB commit
    
    Returns:
        Dict mapping channel_id to success status
    """
    results = {}
    
    for msg in messages:
        channel_id = msg.get("channel_id")
        message_data = msg.get("message_data", {})
        
        if channel_id:
            results[channel_id] = publish_message(
                channel_id=channel_id,
                message_data=message_data,
                event_name=event_name,
                after_commit=after_commit,
                log_debug=False  # Reduce noise for batch
            )
    
    return results


def get_client_config() -> Dict[str, Any]:
    """
    Get configuration that should be passed to the frontend client
    for Socket.IO connection setup.
    
    Returns:
        Dict with client-side configuration
    """
    config = get_config()
    
    return {
        "socketio_url": config.get_external_socketio_url(),
        "websocket_path": config.websocket_path,
        "use_ssl": config.use_ssl,
        "debug_mode": config.debug_mode,
        "deployment_type": config.deployment_type.value,
        # Include CORS origins for client to know what's allowed
        "cors_origins": config.cors_origins,
    }


def diagnose_realtime() -> Dict[str, Any]:
    """
    Perform a diagnostic check on the realtime system.
    
    Returns:
        Dict with diagnostic results and recommendations
    """
    config = get_config()
    validation = validate_realtime_connectivity()
    
    diagnosis = {
        "environment": config.deployment_type.value,
        "config": {
            "socketio_host": config.socketio_host,
            "socketio_port": config.socketio_port,
            "internal_url": config.get_socketio_url(),
            "external_url": config.get_external_socketio_url(),
            "use_ssl": config.use_ssl,
            "proxy_headers_required": config.proxy_headers_required,
        },
        "validation": validation,
        "status": "OK" if not validation["warnings"] else "WARNING",
    }
    
    # Add environment-specific diagnostics
    if config.deployment_type in [DeploymentType.SANDBOX, DeploymentType.SANDBOX_NGROK]:
        diagnosis["sandbox_info"] = {
            "ngrok_tunnel": config.ngrok_tunnel,
            "multiplexer_enabled": config.is_multiplexer_enabled,
            "note": "For ngrok to work with Socket.IO, nginx multiplexer must be running on port 8005"
        }
    
    elif config.deployment_type == DeploymentType.PRODUCTION_TRAEFIK:
        diagnosis["production_info"] = {
            "traefik_host": config.traefik_host,
            "note": "Ensure Traefik routes /socket.io to the nginx sidecar container"
        }
    
    elif config.deployment_type == DeploymentType.FRAPPE_CLOUD:
        diagnosis["frappe_cloud_info"] = {
            "note": "Realtime is managed by Frappe Cloud infrastructure"
        }
    
    return diagnosis


# Convenience function to log diagnostics
def log_realtime_diagnostics():
    """
    Log realtime diagnostic information for debugging.
    """
    diagnosis = diagnose_realtime()
    
    frappe.logger().info("=" * 60)
    frappe.logger().info("[Raven AI Agent] REALTIME DIAGNOSTICS")
    frappe.logger().info("=" * 60)
    frappe.logger().info(f"Environment: {diagnosis['environment']}")
    frappe.logger().info(f"Status: {diagnosis['status']}")
    frappe.logger().info(f"Internal URL: {diagnosis['config']['internal_url']}")
    frappe.logger().info(f"External URL: {diagnosis['config']['external_url']}")
    
    for check in diagnosis["validation"]["checks"]:
        frappe.logger().info(check)
    
    for warning in diagnosis["validation"]["warnings"]:
        frappe.logger().warning(warning)
    
    for rec in diagnosis["validation"]["recommendations"]:
        frappe.logger().info(f"Recommendation: {rec}")
    
    frappe.logger().info("=" * 60)


__all__ = [
    'publish_message',
    'publish_message_batch',
    'get_client_config',
    'diagnose_realtime',
    'log_realtime_diagnostics',
]
