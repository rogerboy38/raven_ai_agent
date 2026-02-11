"""
WhatsApp Channel Adapter
Integration with WhatsApp Business API via Meta Cloud API
"""

import frappe
import requests
from typing import Dict, Optional
from .base import ChannelAdapter, IncomingMessage, OutgoingMessage


class WhatsAppAdapter(ChannelAdapter):
    """
    WhatsApp Business API adapter.
    
    Requires:
    - WHATSAPP_PHONE_NUMBER_ID
    - WHATSAPP_ACCESS_TOKEN
    - WHATSAPP_VERIFY_TOKEN (for webhook verification)
    """
    
    API_VERSION = "v18.0"
    BASE_URL = "https://graph.facebook.com"
    
    def _get_channel_name(self) -> str:
        return "whatsapp"
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.phone_number_id = config.get("phone_number_id")
        self.access_token = config.get("access_token")
        self.verify_token = config.get("verify_token")
    
    def parse_webhook(self, payload: Dict) -> Optional[IncomingMessage]:
        """Parse WhatsApp webhook payload"""
        try:
            entry = payload.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            
            messages = value.get("messages", [])
            if not messages:
                return None
            
            msg = messages[0]
            contacts = value.get("contacts", [{}])
            sender = contacts[0] if contacts else {}
            
            # Handle different message types
            text = ""
            media = None
            
            if msg.get("type") == "text":
                text = msg.get("text", {}).get("body", "")
            elif msg.get("type") == "audio":
                media = {"type": "audio", "id": msg.get("audio", {}).get("id")}
                text = "[Voice Message]"
            elif msg.get("type") == "image":
                media = {"type": "image", "id": msg.get("image", {}).get("id")}
                text = msg.get("image", {}).get("caption", "[Image]")
            
            return IncomingMessage(
                channel="whatsapp",
                channel_user_id=msg.get("from"),
                message_id=msg.get("id"),
                text=text,
                media=media,
                metadata={
                    "sender_name": sender.get("profile", {}).get("name"),
                    "timestamp": msg.get("timestamp")
                }
            )
        except Exception as e:
            frappe.logger().error(f"[WhatsApp] Failed to parse webhook: {e}")
            return None
    
    def send_message(self, recipient_id: str, message: OutgoingMessage) -> Dict:
        """Send message via WhatsApp Business API"""
        url = f"{self.BASE_URL}/{self.API_VERSION}/{self.phone_number_id}/messages"
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_id,
            "type": "text",
            "text": {"body": message.text}
        }
        
        # Handle interactive buttons
        if message.buttons and self.supports_buttons():
            payload["type"] = "interactive"
            payload["interactive"] = {
                "type": "button",
                "body": {"text": message.text},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"]}}
                        for btn in message.buttons[:3]  # WhatsApp limit
                    ]
                }
            }
            del payload["text"]
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            return response.json()
        except Exception as e:
            frappe.logger().error(f"[WhatsApp] Failed to send message: {e}")
            return {"error": str(e)}
    
    def send_typing_indicator(self, recipient_id: str):
        """WhatsApp doesn't support typing indicators via API"""
        pass
    
    def supports_buttons(self) -> bool:
        return True
    
    def verify_webhook(self, params: Dict) -> Optional[str]:
        """Verify webhook subscription from Meta"""
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")
        
        if mode == "subscribe" and token == self.verify_token:
            return challenge
        return None
    
    def download_media(self, media_id: str) -> Optional[bytes]:
        """Download media file from WhatsApp"""
        # First get media URL
        url = f"{self.BASE_URL}/{self.API_VERSION}/{media_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            response = requests.get(url, headers=headers)
            media_url = response.json().get("url")
            
            if media_url:
                media_response = requests.get(media_url, headers=headers)
                return media_response.content
        except Exception as e:
            frappe.logger().error(f"[WhatsApp] Failed to download media: {e}")
        
        return None
