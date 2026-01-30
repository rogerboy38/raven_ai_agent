"""
Slack Channel Adapter
Integration with Slack API
"""

import frappe
import requests
from typing import Dict, Optional
from .base import ChannelAdapter, IncomingMessage, OutgoingMessage


class SlackAdapter(ChannelAdapter):
    """
    Slack API adapter.
    
    Requires:
    - SLACK_BOT_TOKEN
    - SLACK_SIGNING_SECRET (for webhook verification)
    """
    
    BASE_URL = "https://slack.com/api"
    
    def _get_channel_name(self) -> str:
        return "slack"
    
    def __init__(self, config: Dict):
        super().__init__(config)
        self.bot_token = config.get("bot_token")
        self.signing_secret = config.get("signing_secret")
    
    def parse_webhook(self, payload: Dict) -> Optional[IncomingMessage]:
        """Parse Slack event payload"""
        try:
            # Handle URL verification
            if payload.get("type") == "url_verification":
                return None
            
            event = payload.get("event", {})
            event_type = event.get("type")
            
            # Only process messages, ignore bot messages
            if event_type != "message" or event.get("bot_id"):
                return None
            
            # Handle app mentions
            if event_type == "app_mention" or event.get("channel_type") == "im":
                text = event.get("text", "")
                # Remove bot mention from text
                text = " ".join(word for word in text.split() if not word.startswith("<@"))
                
                return IncomingMessage(
                    channel="slack",
                    channel_user_id=event.get("user"),
                    message_id=event.get("ts"),
                    text=text.strip(),
                    metadata={
                        "channel_id": event.get("channel"),
                        "thread_ts": event.get("thread_ts"),
                        "team_id": payload.get("team_id")
                    }
                )
            
            return None
        except Exception as e:
            frappe.logger().error(f"[Slack] Failed to parse webhook: {e}")
            return None
    
    def send_message(self, recipient_id: str, message: OutgoingMessage) -> Dict:
        """Send message via Slack API"""
        url = f"{self.BASE_URL}/chat.postMessage"
        
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "channel": recipient_id,
            "text": message.text,
            "mrkdwn": True
        }
        
        # Add thread_ts if replying in thread
        if message.metadata and message.metadata.get("thread_ts"):
            payload["thread_ts"] = message.metadata["thread_ts"]
        
        # Add blocks for rich formatting
        if message.buttons:
            payload["blocks"] = self._create_button_blocks(message)
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            return response.json()
        except Exception as e:
            frappe.logger().error(f"[Slack] Failed to send message: {e}")
            return {"error": str(e)}
    
    def _create_button_blocks(self, message: OutgoingMessage) -> list:
        """Create Slack blocks with buttons"""
        return [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message.text}
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": btn["title"]},
                        "action_id": btn["id"],
                        "value": btn.get("value", btn["id"])
                    }
                    for btn in message.buttons[:5]  # Slack limit
                ]
            }
        ]
    
    def send_typing_indicator(self, recipient_id: str):
        """Slack doesn't have typing indicators for bots"""
        pass
    
    def supports_buttons(self) -> bool:
        return True
    
    def get_user_info(self, channel_user_id: str) -> Optional[Dict]:
        """Get Slack user info"""
        url = f"{self.BASE_URL}/users.info"
        headers = {"Authorization": f"Bearer {self.bot_token}"}
        
        try:
            response = requests.get(url, headers=headers, params={"user": channel_user_id})
            data = response.json()
            if data.get("ok"):
                user = data.get("user", {})
                return {
                    "id": user.get("id"),
                    "name": user.get("real_name"),
                    "email": user.get("profile", {}).get("email")
                }
        except Exception as e:
            frappe.logger().error(f"[Slack] Failed to get user info: {e}")
        
        return None
