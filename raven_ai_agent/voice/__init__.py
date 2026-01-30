"""
Voice Module - Text-to-Speech Integration
"""

from .elevenlabs import ElevenLabsVoice, VoiceResponseHandler

__all__ = [
    "ElevenLabsVoice",
    "VoiceResponseHandler"
]
