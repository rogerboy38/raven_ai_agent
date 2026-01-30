"""
Session Manager - WebSocket Control Plane
Inspired by OpenClaw's gateway architecture

Manages user sessions across multiple channels with context preservation.
"""

import frappe
import json
import hashlib
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict


@dataclass
class Session:
    """Represents a user session across any channel"""
    session_id: str
    user_id: str
    channel: str  # whatsapp, telegram, slack, raven, web
    channel_user_id: str  # Channel-specific user identifier
    created_at: str
    last_active: str
    context: Dict
    conversation_history: List[Dict]
    metadata: Dict


class SessionManager:
    """
    Central session management for multi-channel AI agent.
    
    Features:
    - Cross-channel session persistence
    - Context carryover between channels
    - Session timeout and cleanup
    - Conversation history management
    """
    
    SESSION_TIMEOUT_MINUTES = 30
    MAX_HISTORY_LENGTH = 50
    
    def __init__(self):
        self.cache_key_prefix = "raven_ai_session:"
    
    def _generate_session_id(self, user_id: str, channel: str) -> str:
        """Generate unique session ID"""
        raw = f"{user_id}:{channel}:{datetime.now().isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    
    def create_session(
        self,
        user_id: str,
        channel: str,
        channel_user_id: str,
        metadata: Dict = None
    ) -> Session:
        """Create a new session"""
        now = datetime.now().isoformat()
        session = Session(
            session_id=self._generate_session_id(user_id, channel),
            user_id=user_id,
            channel=channel,
            channel_user_id=channel_user_id,
            created_at=now,
            last_active=now,
            context={},
            conversation_history=[],
            metadata=metadata or {}
        )
        self._save_session(session)
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve session by ID"""
        cache_key = f"{self.cache_key_prefix}{session_id}"
        data = frappe.cache().get(cache_key)
        if data:
            return Session(**json.loads(data))
        return None
    
    def get_or_create_session(
        self,
        user_id: str,
        channel: str,
        channel_user_id: str
    ) -> Session:
        """Get existing session or create new one"""
        # Try to find existing active session for this user/channel
        existing = self.find_active_session(user_id, channel)
        if existing:
            return existing
        return self.create_session(user_id, channel, channel_user_id)
    
    def find_active_session(self, user_id: str, channel: str) -> Optional[Session]:
        """Find active session for user on specific channel"""
        # In production, this would query a database
        # For now, we use cache with pattern matching
        pattern = f"{self.cache_key_prefix}*"
        keys = frappe.cache().get_keys(pattern)
        
        for key in keys:
            data = frappe.cache().get(key)
            if data:
                session = Session(**json.loads(data))
                if (session.user_id == user_id and 
                    session.channel == channel and
                    self._is_session_active(session)):
                    return session
        return None
    
    def _is_session_active(self, session: Session) -> bool:
        """Check if session is still active (not timed out)"""
        last_active = datetime.fromisoformat(session.last_active)
        timeout = timedelta(minutes=self.SESSION_TIMEOUT_MINUTES)
        return datetime.now() - last_active < timeout
    
    def update_session(
        self,
        session: Session,
        context_update: Dict = None,
        add_message: Dict = None
    ) -> Session:
        """Update session with new context or message"""
        session.last_active = datetime.now().isoformat()
        
        if context_update:
            session.context.update(context_update)
        
        if add_message:
            session.conversation_history.append(add_message)
            # Trim history if too long
            if len(session.conversation_history) > self.MAX_HISTORY_LENGTH:
                session.conversation_history = session.conversation_history[-self.MAX_HISTORY_LENGTH:]
        
        self._save_session(session)
        return session
    
    def _save_session(self, session: Session):
        """Persist session to cache"""
        cache_key = f"{self.cache_key_prefix}{session.session_id}"
        frappe.cache().set(
            cache_key,
            json.dumps(asdict(session)),
            expires_in_sec=self.SESSION_TIMEOUT_MINUTES * 60 * 2
        )
    
    def end_session(self, session_id: str):
        """End and cleanup a session"""
        cache_key = f"{self.cache_key_prefix}{session_id}"
        frappe.cache().delete(cache_key)
    
    def transfer_context(self, from_session: Session, to_channel: str, to_channel_user_id: str) -> Session:
        """Transfer context from one channel to another"""
        new_session = self.create_session(
            user_id=from_session.user_id,
            channel=to_channel,
            channel_user_id=to_channel_user_id,
            metadata={"transferred_from": from_session.channel}
        )
        new_session.context = from_session.context.copy()
        new_session.conversation_history = from_session.conversation_history.copy()
        self._save_session(new_session)
        return new_session


# Global instance
session_manager = SessionManager()
