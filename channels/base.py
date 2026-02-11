"""
Base Channel Adapter
Abstract interface for all messaging channels
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
from dataclasses import dataclass


@dataclass
class IncomingMessage:
    """Standardized incoming message format"""
    channel: str
    channel_user_id: str
    message_id: str
    text: str
    media: Optional[Dict] = None  # {type: "image/audio/video", url: str}
    metadata: Dict = None
    
    def __post_init__(self):
        self.metadata = self.metadata or {}


@dataclass 
class OutgoingMessage:
    """Standardized outgoing message format"""
    text: str
    media: Optional[Dict] = None
    buttons: Optional[list] = None  # Interactive buttons
    metadata: Dict = None
    
    def __post_init__(self):
        self.metadata = self.metadata or {}


class ChannelAdapter(ABC):
    """
    Abstract base class for messaging channel adapters.
    
    Each channel (WhatsApp, Telegram, Slack) implements this interface.
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.channel_name = self._get_channel_name()
    
    @abstractmethod
    def _get_channel_name(self) -> str:
        """Return the channel identifier"""
        pass
    
    @abstractmethod
    def parse_webhook(self, payload: Dict) -> Optional[IncomingMessage]:
        """
        Parse incoming webhook payload into standardized format.
        
        Args:
            payload: Raw webhook data from the channel
            
        Returns:
            IncomingMessage or None if not a valid message
        """
        pass
    
    @abstractmethod
    def send_message(
        self,
        recipient_id: str,
        message: OutgoingMessage
    ) -> Dict:
        """
        Send a message to a user on this channel.
        
        Args:
            recipient_id: Channel-specific user identifier
            message: Standardized message to send
            
        Returns:
            Response from the channel API
        """
        pass
    
    @abstractmethod
    def send_typing_indicator(self, recipient_id: str):
        """Show typing indicator to user"""
        pass
    
    def format_response(self, response: str, metadata: Dict = None) -> OutgoingMessage:
        """Format AI response for this channel"""
        return OutgoingMessage(
            text=response,
            metadata=metadata or {}
        )
    
    def supports_media(self) -> bool:
        """Check if channel supports media messages"""
        return True
    
    def supports_buttons(self) -> bool:
        """Check if channel supports interactive buttons"""
        return False
    
    def get_user_info(self, channel_user_id: str) -> Optional[Dict]:
        """Get user information from channel (if available)"""
        return None
