"""
Base Sub-Agent Class
====================

Abstract base class for all sub-agents in the formulation orchestrator.
Provides common functionality for message handling, logging, and error handling.
"""

import frappe
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime

from ..messages import (
    AgentMessage,
    AgentMessageType,
    AgentChannel,
    WorkflowPhase
)


class BaseSubAgent(ABC):
    """
    Abstract base class for formulation sub-agents.
    
    Each sub-agent implements:
        - name: Unique identifier
        - description: What the agent does
        - handle_message(): Process incoming messages
        - Specific action methods
    """
    
    name: str = "base_sub_agent"
    description: str = "Base sub-agent"
    emoji: str = "🤖"
    phase: WorkflowPhase = None
    
    def __init__(self, channel: AgentChannel = None):
        """
        Initialize the sub-agent.
        
        Args:
            channel: AgentChannel for communication (optional)
        """
        self.channel = channel
        self._initialized_at = datetime.now()
        self._request_count = 0
        self._success_count = 0
        
        # Register self with channel if provided
        if channel:
            channel.register_local_handler(self.name, self.handle_message)
    
    def handle_message(self, message: AgentMessage) -> AgentMessage:
        """
        Handle an incoming message.
        
        Routes to appropriate method based on action.
        
        Args:
            message: Incoming AgentMessage
            
        Returns:
            Response AgentMessage
        """
        self._request_count += 1
        
        try:
            # Log incoming message
            self._log(f"Received: {message.action}", level="debug")
            
            # Validate message
            validation_error = self._validate_message(message)
            if validation_error:
                return message.create_response(
                    success=False,
                    error_message=validation_error,
                    error_code="VALIDATION_ERROR"
                )
            
            # Route to action handler
            handler_method = getattr(self, f"action_{message.action}", None)
            
            if handler_method:
                result = handler_method(message.payload, message)
                self._success_count += 1
                return message.create_response(success=True, result=result)
            else:
                # Try generic process method
                result = self.process(message.action, message.payload, message)
                if result is not None:
                    self._success_count += 1
                    return message.create_response(success=True, result=result)
                else:
                    return message.create_response(
                        success=False,
                        error_message=f"Unknown action: {message.action}",
                        error_code="UNKNOWN_ACTION"
                    )
                    
        except Exception as e:
            self._log(f"Error processing message: {e}", level="error")
            return message.create_response(
                success=False,
                error_message=str(e),
                error_code="PROCESSING_ERROR"
            )
    
    def _validate_message(self, message: AgentMessage) -> Optional[str]:
        """
        Validate an incoming message.
        
        Override in subclass for custom validation.
        
        Returns:
            Error message if invalid, None if valid
        """
        if not message.action:
            return "Message action is required"
        if message.target_agent != self.name and message.target_agent != "*":
            return f"Message not intended for this agent (target: {message.target_agent})"
        return None
    
    @abstractmethod
    def process(self, action: str, payload: Dict, message: AgentMessage) -> Optional[Dict]:
        """
        Process an action. Override in subclass.
        
        Args:
            action: The action to perform
            payload: The message payload
            message: Full message for context
            
        Returns:
            Result dictionary or None if action not handled
        """
        pass
    
    def _log(self, msg: str, level: str = "info"):
        """Log a message with agent context"""
        log_method = getattr(frappe.logger(), level, frappe.logger().info)
        log_method(f"[{self.emoji} {self.name}] {msg}")
    
    def _query_frappe(
        self,
        doctype: str,
        filters: Dict = None,
        fields: List[str] = None,
        limit: int = None,
        order_by: str = None
    ) -> List[Dict]:
        """
        Query Frappe database with error handling.
        
        Args:
            doctype: Frappe DocType to query
            filters: Query filters
            fields: Fields to return
            limit: Result limit
            order_by: Order by clause
            
        Returns:
            List of matching documents
        """
        try:
            return frappe.get_all(
                doctype,
                filters=filters or {},
                fields=fields or ["name"],
                limit_page_length=limit,
                order_by=order_by
            )
        except Exception as e:
            self._log(f"Query error on {doctype}: {e}", level="error")
            return []
    
    def _get_doc(self, doctype: str, name: str) -> Optional[Dict]:
        """
        Get a single document with error handling.
        
        Args:
            doctype: Frappe DocType
            name: Document name
            
        Returns:
            Document as dict or None
        """
        try:
            doc = frappe.get_doc(doctype, name)
            return doc.as_dict()
        except frappe.DoesNotExistError:
            self._log(f"{doctype} '{name}' not found", level="warning")
            return None
        except Exception as e:
            self._log(f"Error getting {doctype} '{name}': {e}", level="error")
            return None
    
    def send_status(self, status: str, details: Dict = None):
        """Send a status update via channel"""
        if self.channel:
            self.channel.broadcast(
                action="agent_status",
                payload={
                    "agent": self.name,
                    "status": status,
                    "details": details or {},
                    "timestamp": datetime.now().isoformat()
                },
                phase=self.phase
            )
    
    def request_from_agent(
        self,
        target: str,
        action: str,
        payload: Dict
    ) -> AgentMessage:
        """
        Send a request to another agent.
        
        Args:
            target: Target agent name
            action: Action to request
            payload: Request payload
            
        Returns:
            Response from target agent
        """
        if not self.channel:
            raise RuntimeError("No channel configured for inter-agent communication")
        
        return self.channel.send_to_agent(
            target=target,
            action=action,
            payload=payload,
            phase=self.phase
        )
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        if self._request_count == 0:
            return 1.0
        return self._success_count / self._request_count
    
    def get_stats(self) -> Dict:
        """Get agent statistics"""
        return {
            "name": self.name,
            "description": self.description,
            "requests": self._request_count,
            "successes": self._success_count,
            "success_rate": self.success_rate,
            "uptime_seconds": (datetime.now() - self._initialized_at).total_seconds()
        }


class MockSubAgent(BaseSubAgent):
    """
    Mock sub-agent for testing.
    Returns predefined responses based on action.
    """
    
    name = "mock_agent"
    description = "Mock agent for testing"
    emoji = "🧪"
    
    def __init__(self, responses: Dict[str, Any] = None, **kwargs):
        super().__init__(**kwargs)
        self.mock_responses = responses or {}
    
    def process(self, action: str, payload: Dict, message: AgentMessage) -> Optional[Dict]:
        """Return mock response for action"""
        if action in self.mock_responses:
            return self.mock_responses[action]
        return {"mock": True, "action": action, "payload": payload}


__all__ = ['BaseSubAgent', 'MockSubAgent']
