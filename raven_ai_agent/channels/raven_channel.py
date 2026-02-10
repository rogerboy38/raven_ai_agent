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
    
    def _send_message(self, text: str, message_type: str = "Text") -> Optional[Dict]:
        """
        Send a message to the channel.
        
        Args:
            text: Message text (supports Markdown)
            message_type: Type of message (Text, Image, File, etc.)
            
        Returns:
            Message document dict or None if failed
        """
        if not self.channel:
            frappe.log_error(
                f"Cannot send message - channel '{self.channel_name}' not initialized",
                "RavenOrchestrator._send_message"
            )
            return None
        
        try:
            # Try to use Raven's message API
            from raven.api.raven_message import send_message
            
            result = send_message(
                channel_id=self.channel.name,
                text=text,
                message_type=message_type
            )
            
            return result
            
        except ImportError:
            # Fallback: Create message document directly
            try:
                message = frappe.get_doc({
                    "doctype": "Raven Message",
                    "channel_id": self.channel.name,
                    "text": text,
                    "message_type": message_type,
                })
                message.insert(ignore_permissions=True)
                frappe.db.commit()
                
                # Publish realtime event (same format as official Raven)
                frappe.publish_realtime(
                    "message_created",
                    {
                        "channel_id": self.channel.name,
                        "sender": frappe.session.user,
                        "message_id": message.name,
                        "message_details": {
                            "text": message.text,
                            "channel_id": message.channel_id,
                            "content": message.content if hasattr(message, 'content') else None,
                            "file": message.file if hasattr(message, 'file') else None,
                            "message_type": message.message_type,
                            "is_edited": 0,
                            "is_thread": message.is_thread if hasattr(message, 'is_thread') else 0,
                            "is_forwarded": message.is_forwarded if hasattr(message, 'is_forwarded') else 0,
                            "is_reply": message.is_reply if hasattr(message, 'is_reply') else 0,
                            "poll_id": message.poll_id if hasattr(message, 'poll_id') else None,
                            "creation": str(message.creation),
                            "owner": message.owner,
                            "modified_by": message.modified_by,
                            "modified": str(message.modified),
                            "linked_message": message.linked_message if hasattr(message, 'linked_message') else None,
                            "replied_message_details": message.replied_message_details if hasattr(message, 'replied_message_details') else None,
                            "link_doctype": message.link_doctype if hasattr(message, 'link_doctype') else None,
                            "link_document": message.link_document if hasattr(message, 'link_document') else None,
                            "message_reactions": message.message_reactions if hasattr(message, 'message_reactions') else None,
                            "thumbnail_width": message.thumbnail_width if hasattr(message, 'thumbnail_width') else None,
                            "thumbnail_height": message.thumbnail_height if hasattr(message, 'thumbnail_height') else None,
                            "file_thumbnail": message.file_thumbnail if hasattr(message, 'file_thumbnail') else None,
                            "image_width": message.image_width if hasattr(message, 'image_width') else None,
                            "image_height": message.image_height if hasattr(message, 'image_height') else None,
                            "name": message.name,
                            "is_bot_message": message.is_bot_message if hasattr(message, 'is_bot_message') else 0,
                            "bot": message.bot if hasattr(message, 'bot') else None,
                            "hide_link_preview": message.hide_link_preview if hasattr(message, 'hide_link_preview') else 0,
                            "blurhash": message.blurhash if hasattr(message, 'blurhash') else None,
                        },
                    },
                    doctype="Raven Channel",
                    docname=self.channel.name,
                    after_commit=True,
                )
                
                return message.as_dict()
                
            except Exception as e:
                frappe.log_error(
                    f"Failed to send message: {e}",
                    "RavenOrchestrator._send_message"
                )
                return None
        
        except Exception as e:
            frappe.log_error(
                f"Error sending Raven message: {e}",
                "RavenOrchestrator._send_message"
            )
            return None
    
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
