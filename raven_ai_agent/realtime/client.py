"""
Socket.IO Client for Raven AI Agent
====================================

A standalone Socket.IO client that uses raven_ai_agent.config for environment-aware
connection configuration. This bypasses Frappe's built-in socketio which may be
broken or misconfigured.

Features:
- Automatic environment detection (sandbox/ngrok, VPS/traefik, production)
- Auto-reconnection with exponential backoff
- Room management (join/leave channels)
- Event emission with optional acknowledgment
- Connection status monitoring
"""

import logging
from typing import Any, Callable, Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import threading
import time

logger = logging.getLogger(__name__)

# Try importing python-socketio
try:
    import socketio
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    logger.warning("python-socketio not installed. Run: pip install python-socketio[client]")


class ConnectionState(Enum):
    """Socket connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class ConnectionConfig:
    """Configuration for Socket.IO connection"""
    url: str
    path: str = "/socket.io"
    transports: List[str] = field(default_factory=lambda: ["polling", "websocket"])
    reconnection: bool = True
    reconnection_attempts: int = 5
    reconnection_delay: float = 1.0
    reconnection_delay_max: float = 30.0
    timeout: float = 20.0
    auth: Optional[Dict[str, Any]] = None


class RealtimeClient:
    """
    Socket.IO client for Raven AI Agent realtime communication.
    
    This client manages the connection to the Socket.IO server independently
    of Frappe's socketio module. It uses the environment configuration from
    raven_ai_agent.config to determine the correct connection URL.
    
    Example:
        client = RealtimeClient()
        client.connect()
        client.emit('my_event', {'data': 'value'}, room='channel-123')
        client.disconnect()
    """
    
    _instance: Optional['RealtimeClient'] = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern for global client access"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config: Optional[ConnectionConfig] = None, auto_connect: bool = False):
        """
        Initialize the realtime client.
        
        Args:
            config: Optional connection configuration. If not provided,
                   configuration is loaded from raven_ai_agent.config
            auto_connect: Whether to connect immediately on initialization
        """
        # Prevent re-initialization of singleton
        if hasattr(self, '_initialized') and self._initialized:
            return
            
        self._initialized = True
        self._config = config
        self._sio: Optional[Any] = None
        self._state = ConnectionState.DISCONNECTED
        self._rooms: set = set()
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._reconnect_count = 0
        
        if not SOCKETIO_AVAILABLE:
            logger.error("python-socketio not available. Client will not function.")
            return
            
        self._setup_client()
        
        if auto_connect:
            self.connect()
    
    def _get_config(self) -> ConnectionConfig:
        """Get connection configuration from environment or use provided config"""
        if self._config:
            return self._config
            
        # Import here to avoid circular imports
        try:
            from raven_ai_agent.config import get_config, get_external_socketio_url
            from raven_ai_agent.config.environment import DeploymentType
            
            env_config = get_config()
            
            # For SANDBOX environments, use localhost directly
            # (avoids network issues when connecting to external ngrok URL from inside the sandbox)
            if env_config.deployment_type in [DeploymentType.SANDBOX, DeploymentType.SANDBOX_NGROK]:
                socketio_port = env_config.socketio_port or 9000
                socketio_url = f"http://localhost:{socketio_port}"
            else:
                # For production/other environments, use external URL
                socketio_url = get_external_socketio_url()
                
                # CRITICAL: python-socketio needs https:// not wss:// for initial handshake
                # The library handles WebSocket upgrade internally after HTTP connection
                if socketio_url.startswith("wss://"):
                    socketio_url = socketio_url.replace("wss://", "https://")
                elif socketio_url.startswith("ws://"):
                    socketio_url = socketio_url.replace("ws://", "http://")
                
                # Remove /socket.io suffix if present (we specify path separately)
                if socketio_url.endswith("/socket.io"):
                    socketio_url = socketio_url[:-10]
            
            return ConnectionConfig(
                url=socketio_url,
                path="/socket.io",
                transports=["polling", "websocket"],
                reconnection=True,
                reconnection_attempts=5,
                timeout=20.0,
            )
        except ImportError:
            logger.warning("Could not import raven_ai_agent.config, using defaults")
            return ConnectionConfig(
                url="http://localhost:9000",
                path="/socket.io",
            )
    
    def _setup_client(self):
        """Setup the Socket.IO client with event handlers"""
        if not SOCKETIO_AVAILABLE:
            return
            
        config = self._get_config()
        
        self._sio = socketio.Client(
            reconnection=config.reconnection,
            reconnection_attempts=config.reconnection_attempts,
            reconnection_delay=config.reconnection_delay,
            reconnection_delay_max=config.reconnection_delay_max,
            logger=False,
            engineio_logger=False,
        )
        
        # Register built-in event handlers
        @self._sio.event
        def connect():
            self._state = ConnectionState.CONNECTED
            self._reconnect_count = 0
            logger.info(f"Connected to Socket.IO server")
            self._trigger_handlers('connect', {})
        
        @self._sio.event
        def disconnect():
            self._state = ConnectionState.DISCONNECTED
            logger.info("Disconnected from Socket.IO server")
            self._trigger_handlers('disconnect', {})
        
        @self._sio.event
        def connect_error(data):
            self._state = ConnectionState.ERROR
            logger.error(f"Connection error: {data}")
            self._trigger_handlers('connect_error', {'error': data})
        
        # Raven-specific events
        @self._sio.on('raven_channel_message')
        def on_channel_message(data):
            logger.debug(f"Channel message received: {data}")
            self._trigger_handlers('raven_channel_message', data)
        
        @self._sio.on('raven_message_updated')
        def on_message_updated(data):
            logger.debug(f"Message updated: {data}")
            self._trigger_handlers('raven_message_updated', data)
        
        @self._sio.on('raven_message_deleted')
        def on_message_deleted(data):
            logger.debug(f"Message deleted: {data}")
            self._trigger_handlers('raven_message_deleted', data)
    
    def _trigger_handlers(self, event: str, data: Any):
        """Trigger registered handlers for an event"""
        handlers = self._event_handlers.get(event, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error(f"Error in event handler for {event}: {e}")
    
    def connect(self) -> bool:
        """
        Connect to the Socket.IO server.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        if not SOCKETIO_AVAILABLE or not self._sio:
            logger.error("Socket.IO client not available")
            return False
            
        if self._state == ConnectionState.CONNECTED:
            logger.debug("Already connected")
            return True
            
        self._state = ConnectionState.CONNECTING
        config = self._get_config()
        
        try:
            logger.info(f"Connecting to {config.url}...")
            self._sio.connect(
                config.url,
                socketio_path=config.path,
                transports=config.transports,
                auth=config.auth,
                wait_timeout=config.timeout,
            )
            return self._state == ConnectionState.CONNECTED
        except Exception as e:
            self._state = ConnectionState.ERROR
            logger.error(f"Failed to connect: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the Socket.IO server"""
        if self._sio and self._state == ConnectionState.CONNECTED:
            self._sio.disconnect()
            self._state = ConnectionState.DISCONNECTED
            self._rooms.clear()
    
    def reconnect(self) -> bool:
        """
        Force reconnection to the server.
        
        Returns:
            bool: True if reconnection successful
        """
        self.disconnect()
        time.sleep(0.5)  # Brief pause before reconnecting
        return self.connect()
    
    def emit(
        self,
        event: str,
        data: Any = None,
        room: Optional[str] = None,
        callback: Optional[Callable] = None
    ) -> bool:
        """
        Emit an event to the server.
        
        Args:
            event: Event name
            data: Event data
            room: Optional room to emit to (via server-side routing)
            callback: Optional callback for acknowledgment
            
        Returns:
            bool: True if emit successful
        """
        if not self._sio or self._state != ConnectionState.CONNECTED:
            logger.warning(f"Cannot emit {event}: not connected")
            return False
            
        try:
            payload = data or {}
            if room:
                payload = {'room': room, 'data': data}
            
            if callback:
                self._sio.emit(event, payload, callback=callback)
            else:
                self._sio.emit(event, payload)
            return True
        except Exception as e:
            logger.error(f"Failed to emit {event}: {e}")
            return False
    
    def join_room(self, room: str) -> bool:
        """
        Join a room for receiving messages.
        
        Args:
            room: Room identifier (e.g., channel name)
            
        Returns:
            bool: True if join request sent successfully
        """
        if not self._sio or self._state != ConnectionState.CONNECTED:
            return False
            
        try:
            self._sio.emit('frappe.subscribe', {'room': room})
            self._rooms.add(room)
            logger.debug(f"Joined room: {room}")
            return True
        except Exception as e:
            logger.error(f"Failed to join room {room}: {e}")
            return False
    
    def leave_room(self, room: str) -> bool:
        """
        Leave a room.
        
        Args:
            room: Room identifier
            
        Returns:
            bool: True if leave request sent successfully
        """
        if not self._sio or self._state != ConnectionState.CONNECTED:
            return False
            
        try:
            self._sio.emit('frappe.unsubscribe', {'room': room})
            self._rooms.discard(room)
            logger.debug(f"Left room: {room}")
            return True
        except Exception as e:
            logger.error(f"Failed to leave room {room}: {e}")
            return False
    
    def on(self, event: str, handler: Callable):
        """
        Register an event handler.
        
        Args:
            event: Event name to listen for
            handler: Callback function(data)
        """
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)
    
    def off(self, event: str, handler: Optional[Callable] = None):
        """
        Remove event handler(s).
        
        Args:
            event: Event name
            handler: Specific handler to remove, or None to remove all
        """
        if event in self._event_handlers:
            if handler:
                self._event_handlers[event] = [
                    h for h in self._event_handlers[event] if h != handler
                ]
            else:
                self._event_handlers[event] = []
    
    @property
    def is_connected(self) -> bool:
        """Check if client is connected"""
        return self._state == ConnectionState.CONNECTED
    
    @property
    def state(self) -> ConnectionState:
        """Get current connection state"""
        return self._state
    
    @property
    def rooms(self) -> set:
        """Get set of currently joined rooms"""
        return self._rooms.copy()
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get detailed connection status.
        
        Returns:
            Dict with connection details
        """
        config = self._get_config()
        return {
            'state': self._state.value,
            'is_connected': self.is_connected,
            'url': config.url,
            'rooms': list(self._rooms),
            'reconnect_count': self._reconnect_count,
            'socketio_available': SOCKETIO_AVAILABLE,
        }


# Module-level singleton instance
_client: Optional[RealtimeClient] = None


def get_socketio_client(auto_connect: bool = True) -> RealtimeClient:
    """
    Get the global Socket.IO client instance.
    
    Args:
        auto_connect: Whether to auto-connect if not connected
        
    Returns:
        RealtimeClient instance
    """
    global _client
    if _client is None:
        _client = RealtimeClient()
    
    if auto_connect and not _client.is_connected:
        _client.connect()
    
    return _client


def emit_event(event: str, data: Any = None, room: Optional[str] = None) -> bool:
    """
    Emit an event using the global client.
    
    Args:
        event: Event name
        data: Event data
        room: Optional target room
        
    Returns:
        bool: Success status
    """
    client = get_socketio_client()
    return client.emit(event, data, room=room)


def emit_to_user(user: str, event: str, data: Any = None) -> bool:
    """
    Emit an event to a specific user.
    
    Args:
        user: User ID or email
        event: Event name
        data: Event data
        
    Returns:
        bool: Success status
    """
    room = f"user:{user}"
    return emit_event(event, data, room=room)


def emit_to_channel(channel: str, event: str, data: Any = None) -> bool:
    """
    Emit an event to a Raven channel.
    
    Args:
        channel: Channel name
        event: Event name
        data: Event data
        
    Returns:
        bool: Success status
    """
    room = f"raven_channel:{channel}"
    return emit_event(event, data, room=room)


def join_room(room: str) -> bool:
    """Join a room using the global client"""
    client = get_socketio_client()
    return client.join_room(room)


def leave_room(room: str) -> bool:
    """Leave a room using the global client"""
    client = get_socketio_client()
    return client.leave_room(room)


def get_connection_status() -> Dict[str, Any]:
    """Get connection status from the global client"""
    client = get_socketio_client(auto_connect=False)
    return client.get_status()


def reconnect() -> bool:
    """Force reconnect the global client"""
    client = get_socketio_client(auto_connect=False)
    return client.reconnect()


def disconnect():
    """Disconnect the global client"""
    global _client
    if _client:
        _client.disconnect()
