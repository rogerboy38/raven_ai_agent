"""
Realtime Communication Module for Raven AI Agent
=================================================

This module provides Socket.IO client management independent of Frappe's socketio.
It uses the environment-aware configuration from raven_ai_agent.config.

Usage:
    from raven_ai_agent.realtime import get_socketio_client, emit_event
    
    # Get configured client
    client = get_socketio_client()
    
    # Emit event to a room
    emit_event('raven_channel_message', {'message': 'Hello'}, room='channel-123')
"""

from .client import (
    RealtimeClient,
    get_socketio_client,
    emit_event,
    emit_to_user,
    emit_to_channel,
    join_room,
    leave_room,
    get_connection_status,
    reconnect,
    disconnect,
)

__all__ = [
    'RealtimeClient',
    'get_socketio_client',
    'emit_event',
    'emit_to_user',
    'emit_to_channel',
    'join_room',
    'leave_room',
    'get_connection_status',
    'reconnect',
    'disconnect',
]
