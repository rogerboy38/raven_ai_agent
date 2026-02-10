"""
Configuration Module for Raven AI Agent
========================================

This module provides environment-aware configuration for the Raven AI Agent.

Usage:
    from raven_ai_agent.config import get_config, get_environment, is_production
    
    # Get current environment
    env = get_environment()  # Returns DeploymentType enum
    
    # Get full configuration
    config = get_config()
    print(f"Socket.IO URL: {config.get_socketio_url()}")
    
    # Check environment type
    if is_production():
        print("Running in production mode")
    
    # Get external URL for clients
    from raven_ai_agent.config import get_external_socketio_url
    client_url = get_external_socketio_url()
    
    # Validate connectivity
    from raven_ai_agent.config import validate_realtime_connectivity
    validation = validate_realtime_connectivity()
    print(validation)
"""

from .environment import (
    DeploymentType,
    EnvironmentConfig,
    EnvironmentDetector,
    KNOWN_ENVIRONMENTS,
    get_environment,
    get_config,
    get_socketio_url,
    get_external_socketio_url,
    get_allowed_origins,
    is_production,
    is_development,
    log_environment_info,
    get_environment_summary,
    validate_realtime_connectivity,
)

from .realtime import (
    publish_message,
    publish_message_batch,
    get_client_config,
    diagnose_realtime,
    log_realtime_diagnostics,
)

__all__ = [
    # Environment
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
    'validate_realtime_connectivity',
    # Realtime
    'publish_message',
    'publish_message_batch',
    'get_client_config',
    'diagnose_realtime',
    'log_realtime_diagnostics',
]
