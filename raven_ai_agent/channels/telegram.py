"""
Telegram Channel Adapter
Integration with Telegram Bot API
"""

import frappe
import requests
from typing import Dict, Optional
from .base import ChannelAdapter, IncomingMessage, OutgoingMessage


class TelegramAdapter(ChannelAdapter):
    """
    Telegram Bot API adapter.
    
    Requires:
    - TELEGRAM_BOT_TOKEN
    """
    
    BASE_URL = "https://api.telegram.org"
    
    def _get_channel_name(self) -> str:
        return "telegram"
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.bot_token = config.get("bot_token")
        self.api_url = f"{self.BASE_URL}/bot{self.bot_token}"
    
    def parse_webhook(self, payload: Dict) -> Optional[IncomingMessage]:
        """Parse Telegram webhook update"""
        try:
            message = payload.get("message") or payload.get("edited_message")
            if not message:
                # Handle callback queries (button presses)
                callback = payload.get("callback_query")
                if callback:
                    return IncomingMessage(
                        channel="telegram",
                        channel_user_id=str(callback["from"]["id"]),
                        message_id=callback["id"],
                        text=callback.get("data", ""),
                        metadata={
                            "type": "callback",
                            "message_id": callback.get("message", {}).get("message_id")
                        }
                    )
                return None
            
            # Handle different message types
            text = ""
            media = None
            
            if "text" in message:
                text = message["text"]
            elif "voice" in message:
                media = {"type": "audio", "file_id": message["voice"]["file_id"]}
                text = "[Voice Message]"
            elif "photo" in message:
                # Get largest photo
                photo = message["photo"][-1]
                media = {"type": "image", "file_id": photo["file_id"]}
                text = message.get("caption", "[Photo]")
            elif "document" in message:
                media = {"type": "document", "file_id": message["document"]["file_id"]}
                text = message.get("caption", "[Document]")
            
            user = message.get("from", {})
            
            return IncomingMessage(
                channel="telegram",
                channel_user_id=str(user.get("id")),
                message_id=str(message.get("message_id")),
                text=text,
                media=media,
                metadata={
                    "sender_name": user.get("first_name", "") + " " + user.get("last_name", ""),
                    "username": user.get("username"),
                    "chat_id": message.get("chat", {}).get("id")
                }
            )
        except Exception as e:
            frappe.logger().error(f"[Telegram] Failed to parse webhook: {e}")
            return None
    
    def send_message(self, recipient_id: str, message: OutgoingMessage) -> Dict:
        """Send message via Telegram Bot API"""
        # Use inline keyboard for buttons
        if message.buttons:
            return self._send_with_buttons(recipient_id, message)
        
        url = f"{self.api_url}/sendMessage"
        payload = {
            "chat_id": recipient_id,
            "text": message.text,
            "parse_mode": "Markdown"
        }
        
        try:
            response = requests.post(url, json=payload)
            return response.json()
        except Exception as e:
            frappe.logger().error(f"[Telegram] Failed to send message: {e}")
            return {"error": str(e)}
    
    def _send_with_buttons(self, recipient_id: str, message: OutgoingMessage) -> Dict:
        """Send message with inline keyboard buttons"""
        url = f"{self.api_url}/sendMessage"
        
        keyboard = [[{"text": btn["title"], "callback_data": btn["id"]}] for btn in message.buttons]
        
        payload = {
            "chat_id": recipient_id,
            "text": message.text,
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": keyboard}
        }
        
        try:
            response = requests.post(url, json=payload)
            return response.json()
        except Exception as e:
            frappe.logger().error(f"[Telegram] Failed to send message with buttons: {e}")
            return {"error": str(e)}
    
    def send_typing_indicator(self, recipient_id: str):
        """Send typing action"""
        url = f"{self.api_url}/sendChatAction"
        payload = {"chat_id": recipient_id, "action": "typing"}
        
        try:
            requests.post(url, json=payload)
        except Exception:
            pass
    
    def supports_buttons(self) -> bool:
        return True
    
    def download_media(self, file_id: str) -> Optional[bytes]:
        """Download file from Telegram"""
        try:
            # Get file path
            url = f"{self.api_url}/getFile"
            response = requests.get(url, params={"file_id": file_id})
            file_path = response.json().get("result", {}).get("file_path")
            
            if file_path:
                download_url = f"{self.BASE_URL}/file/bot{self.bot_token}/{file_path}"
                file_response = requests.get(download_url)
                return file_response.content
        except Exception as e:
            frappe.logger().error(f"[Telegram] Failed to download file: {e}")
        
        return None
    
    def set_webhook(self, webhook_url: str) -> Dict:
        """Set webhook URL for receiving updates"""
        url = f"{self.api_url}/setWebhook"
        payload = {"url": webhook_url}
        
        response = requests.post(url, json=payload)
        return response.json()
