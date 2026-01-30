"""
Channel Adapters - Multi-Platform Messaging
"""

from .base import ChannelAdapter, IncomingMessage, OutgoingMessage
from .whatsapp import WhatsAppAdapter
from .telegram import TelegramAdapter
from .slack import SlackAdapter


def get_channel_adapter(channel: str, config: dict) -> ChannelAdapter:
    """Factory function to get channel adapter"""
    adapters = {
        "whatsapp": WhatsAppAdapter,
        "telegram": TelegramAdapter,
        "slack": SlackAdapter,
    }
    
    adapter_class = adapters.get(channel.lower())
    if not adapter_class:
        raise ValueError(f"Unknown channel: {channel}. Available: {list(adapters.keys())}")
    
    return adapter_class(config)


__all__ = [
    "ChannelAdapter",
    "IncomingMessage",
    "OutgoingMessage",
    "WhatsAppAdapter",
    "TelegramAdapter",
    "SlackAdapter",
    "get_channel_adapter"
]
