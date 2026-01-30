"""
ElevenLabs Voice Integration
Text-to-Speech and Voice Features
"""

import frappe
import requests
from typing import Dict, Optional, List
from io import BytesIO


class ElevenLabsVoice:
    """
    ElevenLabs API integration for voice features.
    
    Features:
    - Text-to-Speech conversion
    - Multiple voice options
    - Voice cloning support
    - Streaming audio
    """
    
    BASE_URL = "https://api.elevenlabs.io/v1"
    
    # Default voices
    VOICES = {
        "rachel": "21m00Tcm4TlvDq8ikWAM",  # Female, calm
        "drew": "29vD33N1CtxCmqQRPOHJ",    # Male, professional
        "clyde": "2EiwWnXFnvU5JabPnv8n",   # Male, warm
        "paul": "5Q0t7uMcjvnagumLfvZi",    # Male, news anchor
        "domi": "AZnzlk1XvdvUeBnXmlld",    # Female, confident
        "bella": "EXAVITQu4vr4xnSDxMaL",   # Female, soft
    }
    
    def __init__(self, api_key: str, default_voice: str = "rachel"):
        self.api_key = api_key
        self.default_voice_id = self.VOICES.get(default_voice, default_voice)
        self.headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }
    
    def text_to_speech(
        self,
        text: str,
        voice_id: str = None,
        model_id: str = "eleven_monolingual_v1",
        stability: float = 0.5,
        similarity_boost: float = 0.75
    ) -> Optional[bytes]:
        """
        Convert text to speech audio.
        
        Args:
            text: Text to convert
            voice_id: Voice ID or name from VOICES dict
            model_id: ElevenLabs model to use
            stability: Voice stability (0-1)
            similarity_boost: Voice similarity (0-1)
            
        Returns:
            Audio data as bytes (MP3 format)
        """
        # Resolve voice ID
        vid = voice_id or self.default_voice_id
        if vid in self.VOICES:
            vid = self.VOICES[vid]
        
        url = f"{self.BASE_URL}/text-to-speech/{vid}"
        
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost
            }
        }
        
        try:
            response = requests.post(
                url,
                headers=self.headers,
                json=payload
            )
            
            if response.status_code == 200:
                return response.content
            else:
                frappe.logger().error(f"[ElevenLabs] TTS failed: {response.text}")
                return None
                
        except Exception as e:
            frappe.logger().error(f"[ElevenLabs] TTS error: {e}")
            return None
    
    def text_to_speech_stream(
        self,
        text: str,
        voice_id: str = None
    ):
        """
        Stream text-to-speech audio.
        
        Yields audio chunks for streaming playback.
        """
        vid = voice_id or self.default_voice_id
        if vid in self.VOICES:
            vid = self.VOICES[vid]
        
        url = f"{self.BASE_URL}/text-to-speech/{vid}/stream"
        
        payload = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        
        try:
            with requests.post(url, headers=self.headers, json=payload, stream=True) as response:
                if response.status_code == 200:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            yield chunk
        except Exception as e:
            frappe.logger().error(f"[ElevenLabs] Stream error: {e}")
    
    def get_voices(self) -> List[Dict]:
        """Get list of available voices"""
        url = f"{self.BASE_URL}/voices"
        
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                return [
                    {
                        "voice_id": v["voice_id"],
                        "name": v["name"],
                        "category": v.get("category"),
                        "labels": v.get("labels", {})
                    }
                    for v in data.get("voices", [])
                ]
        except Exception as e:
            frappe.logger().error(f"[ElevenLabs] Get voices error: {e}")
        
        return []
    
    def get_user_info(self) -> Optional[Dict]:
        """Get user subscription info and usage"""
        url = f"{self.BASE_URL}/user"
        
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            frappe.logger().error(f"[ElevenLabs] Get user info error: {e}")
        
        return None


class VoiceResponseHandler:
    """
    Handles voice responses in the AI agent.
    
    Decides when to respond with voice vs text based on:
    - User preference
    - Message type
    - Channel capabilities
    """
    
    def __init__(self, elevenlabs: ElevenLabsVoice):
        self.tts = elevenlabs
        self.voice_enabled = True
    
    def should_use_voice(self, context: Dict) -> bool:
        """Determine if response should be voice"""
        # Voice if user sent voice message
        if context.get("input_type") == "voice":
            return True
        
        # Voice if explicitly requested
        if context.get("voice_requested"):
            return True
        
        # Check user preferences
        if context.get("user_prefers_voice"):
            return True
        
        return False
    
    def create_voice_response(
        self,
        text: str,
        voice: str = None
    ) -> Optional[Dict]:
        """
        Create voice response from text.
        
        Returns dict with audio data and metadata.
        """
        audio_data = self.tts.text_to_speech(text, voice_id=voice)
        
        if audio_data:
            return {
                "type": "audio",
                "format": "mp3",
                "data": audio_data,
                "text": text,  # Include text for accessibility
                "duration_estimate": len(text) / 15  # Rough estimate in seconds
            }
        
        return None
