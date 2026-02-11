"""
Agent Communication Protocol for Formulation Orchestrator
==========================================================

Defines the message contracts and AgentChannel for inter-agent communication.
Integrates with Raven's channel system for pub/sub messaging.

Usage:
    from raven_ai_agent.skills.formulation_orchestrator.messages import (
        AgentMessage, AgentChannel, AgentMessageType
    )
    
    # Send message between agents
    channel = AgentChannel()
    response = channel.send_to_agent(
        target="batch_selector",
        action="select_batches",
        payload={"item_code": "ITEM-001"}
    )
"""

import frappe
import uuid
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod


# ===========================================
# Message Types and Enums
# ===========================================

class AgentMessageType(Enum):
    """Types of messages exchanged between agents"""
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    STATUS = "status"
    BROADCAST = "broadcast"
    HANDOFF = "handoff"


class AgentStatus(Enum):
    """Status of an agent during workflow execution"""
    IDLE = "idle"
    PROCESSING = "processing"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowPhase(Enum):
    """Phases of the formulation workflow"""
    REQUEST_ANALYSIS = "request_analysis"
    BATCH_SELECTION = "batch_selection"
    TDS_COMPLIANCE = "tds_compliance"
    COST_CALCULATION = "cost_calculation"
    OPTIMIZATION = "optimization"
    REPORT_GENERATION = "report_generation"


# ===========================================
# Message Data Classes
# ===========================================

@dataclass
class AgentMessage:
    """
    Standard message format for inter-agent communication.
    
    Compatible with Raven's channel message format while adding
    agent-specific routing and workflow tracking.
    """
    
    # Header - Required
    message_id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    message_type: AgentMessageType = AgentMessageType.REQUEST
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Routing - Required
    source_agent: str = ""
    target_agent: str = ""
    
    # Payload - Required
    action: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    
    # Context - Optional
    workflow_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    phase: Optional[WorkflowPhase] = None
    priority: int = 50  # 0-100, higher = more important
    
    # Response fields - Set by receiving agent
    success: Optional[bool] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    result: Optional[Any] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        data['message_type'] = self.message_type.value
        data['timestamp'] = self.timestamp.isoformat()
        if self.phase:
            data['phase'] = self.phase.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'AgentMessage':
        """Create from dictionary"""
        if 'message_type' in data and isinstance(data['message_type'], str):
            data['message_type'] = AgentMessageType(data['message_type'])
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        if 'phase' in data and isinstance(data['phase'], str):
            data['phase'] = WorkflowPhase(data['phase'])
        return cls(**data)
    
    def create_response(
        self,
        success: bool,
        result: Any = None,
        error_message: str = None,
        error_code: str = None
    ) -> 'AgentMessage':
        """Create a response message for this request"""
        return AgentMessage(
            message_type=AgentMessageType.RESPONSE if success else AgentMessageType.ERROR,
            source_agent=self.target_agent,
            target_agent=self.source_agent,
            action=self.action,
            workflow_id=self.workflow_id,
            parent_message_id=self.message_id,
            phase=self.phase,
            success=success,
            result=result,
            error_message=error_message,
            error_code=error_code,
            payload={}
        )


@dataclass
class WorkflowState:
    """Tracks the state of a formulation workflow"""
    workflow_id: str = field(default_factory=lambda: f"wf_{uuid.uuid4().hex[:12]}")
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Request info
    request: Dict[str, Any] = field(default_factory=dict)
    
    # Phase results
    phases: Dict[str, Dict] = field(default_factory=dict)
    
    # Current status
    current_phase: Optional[WorkflowPhase] = None
    status: AgentStatus = AgentStatus.IDLE
    
    # Message history
    message_history: List[str] = field(default_factory=list)  # List of message_ids
    
    def update_phase(self, phase: WorkflowPhase, result: Dict):
        """Update a phase result"""
        self.phases[phase.value] = result
        self.current_phase = phase
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'workflow_id': self.workflow_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'request': self.request,
            'phases': self.phases,
            'current_phase': self.current_phase.value if self.current_phase else None,
            'status': self.status.value,
            'message_history': self.message_history
        }


# ===========================================
# Agent Channel - Inter-Agent Communication
# ===========================================

class AgentChannel:
    """
    Channel for inter-agent communication within Raven.
    
    Provides:
    - Synchronous message passing between agents
    - Pub/Sub via Frappe realtime events
    - Message history tracking
    - Error handling and retries
    
    Usage:
        channel = AgentChannel(source_agent="orchestrator")
        
        # Synchronous call
        result = channel.send_to_agent(
            target="batch_selector",
            action="select_batches",
            payload={"item_code": "ITEM-001"}
        )
        
        # Async broadcast
        channel.broadcast(
            action="workflow_status",
            payload={"status": "completed"}
        )
    """
    
    # Registry of agent handlers
    _handlers: Dict[str, Callable] = {}
    _message_log: List[AgentMessage] = []
    
    def __init__(self, source_agent: str = "orchestrator", workflow_id: str = None):
        self.source_agent = source_agent
        self.workflow_id = workflow_id or f"wf_{uuid.uuid4().hex[:12]}"
        self._local_handlers: Dict[str, Callable] = {}
    
    @classmethod
    def register_handler(cls, agent_name: str, handler: Callable):
        """
        Register a handler for an agent.
        
        Args:
            agent_name: Name of the agent
            handler: Callable that accepts AgentMessage and returns AgentMessage
        """
        cls._handlers[agent_name] = handler
        frappe.logger().info(f"[AgentChannel] Registered handler for: {agent_name}")
    
    @classmethod
    def get_handler(cls, agent_name: str) -> Optional[Callable]:
        """Get the registered handler for an agent"""
        return cls._handlers.get(agent_name)
    
    def register_local_handler(self, agent_name: str, handler: Callable):
        """Register a local handler (for this channel instance only)"""
        self._local_handlers[agent_name] = handler
    
    def send_to_agent(
        self,
        target: str,
        action: str,
        payload: Dict[str, Any],
        phase: WorkflowPhase = None,
        priority: int = 50,
        timeout: int = 30
    ) -> AgentMessage:
        """
        Send a synchronous message to another agent.
        
        Args:
            target: Target agent name
            action: Action to perform
            payload: Data payload
            phase: Current workflow phase
            priority: Message priority (0-100)
            timeout: Timeout in seconds
            
        Returns:
            Response AgentMessage from the target agent
        """
        # Create the message
        message = AgentMessage(
            message_type=AgentMessageType.REQUEST,
            source_agent=self.source_agent,
            target_agent=target,
            action=action,
            payload=payload,
            workflow_id=self.workflow_id,
            phase=phase,
            priority=priority
        )
        
        # Log the outgoing message
        self._log_message(message)
        
        # Try to find handler
        handler = self._local_handlers.get(target) or self._handlers.get(target)
        
        if handler:
            try:
                # Direct invocation
                response = handler(message)
                self._log_message(response)
                return response
            except Exception as e:
                error_response = message.create_response(
                    success=False,
                    error_message=str(e),
                    error_code="HANDLER_ERROR"
                )
                self._log_message(error_response)
                return error_response
        else:
            # Try Frappe realtime pub/sub
            return self._send_via_realtime(message, timeout)
    
    def _send_via_realtime(self, message: AgentMessage, timeout: int) -> AgentMessage:
        """Send message via Frappe realtime events"""
        try:
            # Publish the message
            frappe.publish_realtime(
                event=f"agent_message:{message.target_agent}",
                message=message.to_dict(),
                after_commit=False
            )
            
            # For now, return a pending response
            # In production, implement proper async waiting
            return message.create_response(
                success=True,
                result={"status": "message_sent", "awaiting_response": True}
            )
        except Exception as e:
            return message.create_response(
                success=False,
                error_message=f"Failed to send via realtime: {e}",
                error_code="REALTIME_ERROR"
            )
    
    def broadcast(
        self,
        action: str,
        payload: Dict[str, Any],
        phase: WorkflowPhase = None
    ):
        """
        Broadcast a message to all listening agents.
        
        Args:
            action: Action/event name
            payload: Data payload
            phase: Current workflow phase
        """
        message = AgentMessage(
            message_type=AgentMessageType.BROADCAST,
            source_agent=self.source_agent,
            target_agent="*",  # Broadcast indicator
            action=action,
            payload=payload,
            workflow_id=self.workflow_id,
            phase=phase
        )
        
        self._log_message(message)
        
        # Publish to all subscribers
        frappe.publish_realtime(
            event="agent_broadcast",
            message=message.to_dict(),
            after_commit=False
        )
    
    def handoff(
        self,
        target: str,
        context: Dict[str, Any],
        reason: str = ""
    ) -> AgentMessage:
        """
        Hand off workflow control to another agent.
        
        Args:
            target: Target agent to hand off to
            context: Full context to pass
            reason: Reason for handoff
            
        Returns:
            Response from the target agent
        """
        return self.send_to_agent(
            target=target,
            action="handoff",
            payload={
                "context": context,
                "reason": reason,
                "workflow_id": self.workflow_id
            },
            priority=90  # High priority for handoffs
        )
    
    def _log_message(self, message: AgentMessage):
        """Log a message for history tracking"""
        self._message_log.append(message)
        
        # Also log to Frappe logger for debugging
        frappe.logger().debug(
            f"[AgentChannel] {message.source_agent} -> {message.target_agent}: "
            f"{message.action} ({message.message_type.value})"
        )
    
    @classmethod
    def get_message_history(cls, workflow_id: str = None) -> List[Dict]:
        """Get message history, optionally filtered by workflow"""
        messages = cls._message_log
        if workflow_id:
            messages = [m for m in messages if m.workflow_id == workflow_id]
        return [m.to_dict() for m in messages]
    
    @classmethod
    def clear_history(cls):
        """Clear message history"""
        cls._message_log = []


# ===========================================
# Message Factory - Convenience Methods
# ===========================================

class MessageFactory:
    """Factory for creating common message types"""
    
    @staticmethod
    def batch_selection_request(
        item_code: str,
        warehouse: str,
        quantity: float,
        production_date: str,
        workflow_id: str = None
    ) -> AgentMessage:
        """Create a batch selection request message"""
        return AgentMessage(
            message_type=AgentMessageType.REQUEST,
            source_agent="orchestrator",
            target_agent="batch_selector",
            action="select_batches",
            payload={
                "item_code": item_code,
                "warehouse": warehouse,
                "quantity_required": quantity,
                "production_date": production_date
            },
            workflow_id=workflow_id,
            phase=WorkflowPhase.BATCH_SELECTION
        )
    
    @staticmethod
    def tds_compliance_request(
        batches: List[Dict],
        tds_requirements: Dict,
        workflow_id: str = None
    ) -> AgentMessage:
        """Create a TDS compliance check request"""
        return AgentMessage(
            message_type=AgentMessageType.REQUEST,
            source_agent="orchestrator",
            target_agent="tds_compliance",
            action="validate_compliance",
            payload={
                "batches": batches,
                "tds_requirements": tds_requirements
            },
            workflow_id=workflow_id,
            phase=WorkflowPhase.TDS_COMPLIANCE
        )
    
    @staticmethod
    def cost_calculation_request(
        batches: List[Dict],
        quantity: float,
        workflow_id: str = None
    ) -> AgentMessage:
        """Create a cost calculation request"""
        return AgentMessage(
            message_type=AgentMessageType.REQUEST,
            source_agent="orchestrator",
            target_agent="cost_calculator",
            action="calculate_costs",
            payload={
                "batches": batches,
                "quantity": quantity
            },
            workflow_id=workflow_id,
            phase=WorkflowPhase.COST_CALCULATION
        )
    
    @staticmethod
    def optimization_request(
        workflow_state: Dict,
        constraints: Dict,
        workflow_id: str = None
    ) -> AgentMessage:
        """Create an optimization request"""
        return AgentMessage(
            message_type=AgentMessageType.REQUEST,
            source_agent="orchestrator",
            target_agent="optimization_engine",
            action="optimize",
            payload={
                "workflow_state": workflow_state,
                "constraints": constraints
            },
            workflow_id=workflow_id,
            phase=WorkflowPhase.OPTIMIZATION
        )
    
    @staticmethod
    def report_generation_request(
        workflow_state: Dict,
        report_type: str = "full",
        workflow_id: str = None
    ) -> AgentMessage:
        """Create a report generation request"""
        return AgentMessage(
            message_type=AgentMessageType.REQUEST,
            source_agent="orchestrator",
            target_agent="report_generator",
            action="generate_report",
            payload={
                "workflow_state": workflow_state,
                "report_type": report_type
            },
            workflow_id=workflow_id,
            phase=WorkflowPhase.REPORT_GENERATION
        )


# ===========================================
# Exports
# ===========================================

__all__ = [
    'AgentMessage',
    'AgentMessageType',
    'AgentStatus',
    'WorkflowPhase',
    'WorkflowState',
    'AgentChannel',
    'MessageFactory'
]
