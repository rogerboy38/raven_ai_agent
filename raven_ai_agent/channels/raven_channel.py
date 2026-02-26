"""
Raven Channel - Inter-Agent and Team Communication
===================================================

Provides communication via Raven channels for:
1. AI Agent → Implementation Team (specs, questions, approvals)
2. Agent → Agent (workflow orchestration)

Integrates with Frappe's Raven messaging system for real-time communication.
"""

import frappe
from typing import Dict, List, Optional, Any
from datetime import datetime

# Import channel utilities for realtime events
from raven_ai_agent.api.channel_utils import publish_message_created_event


class RavenOrchestrator:
    """
    Orchestrator communication via Raven channels.
    
    Enables real-time messaging between AI agents and human team members
    using Raven's built-in channel infrastructure.
    
    Usage:
        orchestrator = RavenOrchestrator("formulation-orchestration")
        
        # Send a phase specification
        orchestrator.send_spec(phase=2, content="...")
        
        # Ask a question
        orchestrator.send_question("Should we use Bin or Batch AMB?")
        
        # Send approval
        orchestrator.send_approval(phase=1, status="approved", notes="All tests pass")
    """
    
    def __init__(self, channel_name: str = "formulation-orchestration"):
        """
        Initialize the orchestrator with a Raven channel.
        
        Args:
            channel_name: Name of the Raven channel to use
        """
        self.channel_name = channel_name
        self._channel = None
        self._initialized = False
    
    @property
    def channel(self):
        """Lazy load the channel document."""
        if not self._channel:
            try:
                self._channel = frappe.get_doc("Raven Channel", self.channel_name)
                self._initialized = True
            except frappe.DoesNotExistError:
                frappe.log_error(
                    f"Raven channel '{self.channel_name}' not found. Please create it first.",
                    "RavenOrchestrator"
                )
                self._initialized = False
        return self._channel
    #
    def _send_message(self, text: str, message_type: str = "Text") -> Optional[Dict]:
        """
        Send a message to the channel using direct database creation + realtime event.
        """
        if not self.channel:
            frappe.log_error("Cannot send message: No channel associated", "RavenOrchestrator")
            return None
        
        try:
            # Get the Frappe user for the bot
            bot_user = frappe.db.get_value("User", {"email": "raven@sysmayal.com"}, "name")
            if not bot_user:
                frappe.log_error("Raven AI bot user not found in User", "RavenOrchestrator")
                return None
            
            # Create message directly in database - SIN el campo 'bot'
            message_doc = frappe.get_doc({
                "doctype": "Raven Message",
                "channel_id": self.channel.name,
                "text": text,
                "message_type": message_type,
                "owner": bot_user,
                "is_bot_message": 1  # Este campo sí existe en la tabla
                # ELIMINADO: "bot": "Raven AI" - causa error de validación
            })
            
            message_doc.insert(ignore_permissions=True)
            frappe.db.commit()
            
            # Publish realtime event
            from raven_ai_agent.api.channel_utils import publish_message_created_event
            publish_message_created_event(message_doc, self.channel.name)
            
            frappe.log_error(f"Message sent successfully to channel {self.channel.name}", "RavenOrchestrator")
            return message_doc.as_dict()
        
        except Exception as e:
            frappe.log_error(f"Error sending message: {str(e)}", "RavenOrchestrator")
            return None
    #
    
    def send_spec(self, phase: int, content: str, title: str = None) -> Optional[Dict]:
        """
        Send a phase specification to the channel.
        
        Args:
            phase: Phase number
            content: Specification content (Markdown)
            title: Optional custom title
            
        Returns:
            Message result or None
        """
        title = title or f"Phase {phase} Specification"
        
        message = f"""## 📋 {title}

{content}

---
*Sent by Orchestrator AI at {datetime.now().strftime('%Y-%m-%d %H:%M')}*

👍 React to acknowledge receipt
"""
        return self._send_message(message)
    
    def send_question(
        self, 
        question: str, 
        context: str = "",
        options: List[str] = None
    ) -> Optional[Dict]:
        """
        Ask a question to the implementation team.
        
        Args:
            question: The question to ask
            context: Additional context
            options: Optional list of answer options
            
        Returns:
            Message result or None
        """
        message = f"""## ❓ Question from Orchestrator

**Question:** {question}
"""
        
        if context:
            message += f"\n**Context:** {context}\n"
        
        if options:
            message += "\n**Options:**\n"
            emojis = ["👍", "👎", "💬", "🔄", "❓"]
            for i, option in enumerate(options):
                emoji = emojis[i] if i < len(emojis) else "•"
                message += f"- {emoji} {option}\n"
        
        message += "\nPlease respond in this thread 👇"
        
        return self._send_message(message)
    
    def send_approval(
        self, 
        phase: int, 
        status: str, 
        notes: str = "",
        checklist: List[Dict] = None
    ) -> Optional[Dict]:
        """
        Send phase approval/feedback.
        
        Args:
            phase: Phase number
            status: Status string (approved, pending, rejected, needs_revision)
            notes: Additional notes
            checklist: List of checklist items [{item, status, notes}]
            
        Returns:
            Message result or None
        """
        status_config = {
            "approved": ("✅", "APPROVED"),
            "pending": ("🔄", "PENDING"),
            "rejected": ("❌", "REJECTED"),
            "needs_revision": ("📝", "NEEDS REVISION"),
        }
        
        emoji, status_text = status_config.get(status.lower(), ("ℹ️", status.upper()))
        
        message = f"""## {emoji} Phase {phase} Review

**Status:** {status_text}
"""
        
        if notes:
            message += f"\n{notes}\n"
        
        if checklist:
            message += "\n### Checklist\n"
            for item in checklist:
                item_status = "✅" if item.get("status") == "pass" else "❌" if item.get("status") == "fail" else "⏳"
                message += f"- {item_status} {item.get('item', '')}"
                if item.get("notes"):
                    message += f" - {item['notes']}"
                message += "\n"
        
        message += f"\n---\n*Reviewed at {datetime.now().strftime('%Y-%m-%d %H:%M')}*"
        
        return self._send_message(message)
    
    def send_test_report(
        self, 
        phase: int,
        test_results: List[Dict],
        execution_time: float = None,
        summary: str = None
    ) -> Optional[Dict]:
        """
        Send a test report to the channel.
        
        Args:
            phase: Phase number
            test_results: List of test results [{suite, tests, status, notes}]
            execution_time: Total execution time in seconds
            summary: Optional summary text
            
        Returns:
            Message result or None
        """
        total_tests = sum(t.get("tests", 0) for t in test_results)
        passed_tests = sum(t.get("tests", 0) for t in test_results if t.get("status") == "pass")
        all_pass = passed_tests == total_tests
        
        status_emoji = "✅" if all_pass else "❌"
        
        message = f"""## 🧪 Test Report: Phase {phase}

| Suite | Tests | Status |
|-------|-------|--------|
"""
        
        for result in test_results:
            status_icon = "✅" if result.get("status") == "pass" else "❌"
            message += f"| {result.get('suite', 'Unknown')} | {result.get('tests', 0)} | {status_icon} |\n"
        
        message += f"| **TOTAL** | **{total_tests}** | {status_emoji} **{'ALL PASS' if all_pass else f'{passed_tests}/{total_tests} PASS'}** |\n"
        
        if execution_time:
            message += f"\n*Execution time: {execution_time:.3f}s*\n"
        
        if summary:
            message += f"\n### Summary\n{summary}\n"
        
        return self._send_message(message)
    
    def send_workflow_update(
        self,
        workflow_id: str,
        current_phase: str,
        status: str,
        details: Dict = None
    ) -> Optional[Dict]:
        """
        Send a workflow status update.
        
        Args:
            workflow_id: Workflow identifier
            current_phase: Current phase name
            status: Current status
            details: Additional details dict
            
        Returns:
            Message result or None
        """
        status_icons = {
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "waiting": "⏳",
            "paused": "⏸️",
        }
        
        icon = status_icons.get(status.lower(), "ℹ️")
        
        message = f"""## {icon} Workflow Update

**Workflow ID:** `{workflow_id}`
**Phase:** {current_phase}
**Status:** {status.upper()}
"""
        
        if details:
            message += "\n**Details:**\n```json\n"
            import json
            message += json.dumps(details, indent=2, default=str)
            message += "\n```\n"
        
        message += f"\n*Updated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        
        return self._send_message(message)
    
    def send_agent_handoff(
        self,
        from_agent: str,
        to_agent: str,
        context: Dict,
        reason: str = ""
    ) -> Optional[Dict]:
        """
        Notify about an agent handoff.
        
        Args:
            from_agent: Source agent name
            to_agent: Target agent name
            context: Handoff context
            reason: Reason for handoff
            
        Returns:
            Message result or None
        """
        message = f"""## 🔀 Agent Handoff

**From:** `{from_agent}`
**To:** `{to_agent}`
"""
        
        if reason:
            message += f"**Reason:** {reason}\n"
        
        if context:
            message += "\n**Context:**\n```json\n"
            import json
            message += json.dumps(context, indent=2, default=str)
            message += "\n```\n"
        
        return self._send_message(message)
    
    def broadcast_alert(
        self,
        alert_type: str,
        title: str,
        message_content: str,
        severity: str = "info"
    ) -> Optional[Dict]:
        """
        Broadcast an alert to the channel.
        
        Args:
            alert_type: Type of alert (test, build, deploy, error)
            title: Alert title
            message_content: Alert content
            severity: Severity level (info, warning, error, critical)
            
        Returns:
            Message result or None
        """
        severity_config = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨",
        }
        
        icon = severity_config.get(severity.lower(), "ℹ️")
        
        message = f"""## {icon} Alert: {title}

**Type:** {alert_type}
**Severity:** {severity.upper()}

{message_content}

---
*Alert generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
        
        return self._send_message(message)
    
    @staticmethod
    def create_channel(
        channel_name: str,
        description: str = "",
        is_private: bool = True,
        members: List[str] = None
    ) -> Optional[Dict]:
        """
        Create a new Raven channel.
        
        Args:
            channel_name: Channel name (slug format)
            description: Channel description
            is_private: Whether the channel is private
            members: List of user IDs to add
            
        Returns:
            Channel document dict or None
        """
        try:
            # Check if channel already exists
            if frappe.db.exists("Raven Channel", channel_name):
                return frappe.get_doc("Raven Channel", channel_name).as_dict()
            
            channel = frappe.get_doc({
                "doctype": "Raven Channel",
                "channel_name": channel_name,
                "channel_description": description,
                "type": "Private" if is_private else "Public",
            })
            channel.insert(ignore_permissions=True)
            
            # Add members if provided
            if members:
                for member in members:
                    try:
                        frappe.get_doc({
                            "doctype": "Raven Channel Member",
                            "channel_id": channel.name,
                            "user_id": member,
                        }).insert(ignore_permissions=True)
                    except Exception as e:
                        frappe.log_error(f"Failed to add member {member}: {e}", "RavenOrchestrator")
            
            frappe.db.commit()
            
            return channel.as_dict()
            
        except Exception as e:
            frappe.log_error(f"Failed to create channel: {e}", "RavenOrchestrator.create_channel")
            return None


# ===========================================
# Convenience Functions
# ===========================================

def get_orchestrator(channel_name: str = "formulation-orchestration") -> RavenOrchestrator:
    """Get a RavenOrchestrator instance for the specified channel."""
    return RavenOrchestrator(channel_name)


def send_phase_spec(phase: int, content: str) -> Optional[Dict]:
    """Quick function to send a phase specification."""
    return get_orchestrator().send_spec(phase, content)


def send_question(question: str, context: str = "") -> Optional[Dict]:
    """Quick function to send a question."""
    return get_orchestrator().send_question(question, context)


def send_approval(phase: int, status: str, notes: str = "") -> Optional[Dict]:
    """Quick function to send phase approval."""
    return get_orchestrator().send_approval(phase, status, notes)


__all__ = [
    'RavenOrchestrator',
    'get_orchestrator',
    'send_phase_spec',
    'send_question',
    'send_approval',
]
