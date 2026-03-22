"""
Phase 9 Scenario Script: SO Lifecycle + Manufacturing Delay + Payment Edge

This script simulates a realistic conversation flow with the Raven AI Agent
to test the multi-agent orchestration and context memory systems.

Usage:
    from raven_ai_agent.cli.so_lifecycle_scenario import run_so_lifecycle_scenario, main
    run_so_lifecycle_scenario()
    main()  # runs with default settings
"""
import frappe
from unittest.mock import MagicMock, patch
from raven_ai_agent.api.router import handle_raven_message


# Default configuration - adjust for your environment
SITE_USER = "administrator@yourcompany.com"  # change if needed
CHANNEL_ID = "Raven Dev Channel"              # change if needed

# Global to capture responses
_captured_responses = []


def create_mock_message(text: str, user: str = SITE_USER, channel_id: str = CHANNEL_ID):
    """
    Create a mock Raven Message document for testing.
    
    Args:
        text: The message text
        user: The user who sent the message
        channel_id: The channel ID
        
    Returns:
        Mock Raven Message document
    """
    doc = MagicMock()
    doc.text = text
    doc.owner = user
    doc.channel_id = channel_id
    doc.is_bot_message = False
    doc.name = f"test_msg_{frappe.utils.now()}"
    return doc


def mock_send_bot_message(doc, text):
    """
    Mock for _send_bot_message that captures the response instead of sending.
    This allows us to capture what the bot would have responded.
    """
    global _captured_responses
    _captured_responses.append(text)
    print(f"<< Raven: {text}")
    return text


def run_so_lifecycle_scenario(
    user: str = SITE_USER,
    channel_id: str = CHANNEL_ID,
    so_name: str = "SO-00001"
) -> list:
    """
    Run the Phase 9 scenario: SO lifecycle + manufacturing delay + payment edge.
    
    This executes a sequence of commands that test:
    - Basic SO queries (list, status)
    - Multi-agent pipelines (diagnose and fix, workflow run)
    - Payment checking
    - Context memory across turns
    
    Args:
        user: The user to run as
        channel_id: The channel to send messages to
        so_name: The Sales Order to test with
        
    Returns:
        List of (message, response) tuples for transcript capture
    """
    global _captured_responses
    _captured_responses = []
    transcript = []
    
    def send(msg: str):
        """Send a message and capture the response."""
        print(f"\n>> {user}: {msg}")
        try:
            # Create a mock Raven Message document
            mock_doc = create_mock_message(msg, user=user, channel_id=channel_id)
            
            # Mock _send_bot_message to capture response instead of sending
            with patch('raven_ai_agent.api.router._send_bot_message', side_effect=mock_send_bot_message):
                # Call handle_raven_message with the mock doc
                handle_raven_message(doc=mock_doc)
            
            # Get captured response
            response = _captured_responses[-1] if _captured_responses else None
            transcript.append((msg, response))
            return response
        except Exception as e:
            print(f"<< ERROR: {e}")
            import traceback
            traceback.print_exc()
            transcript.append((msg, f"ERROR: {e}"))
            return str(e)
    
    print("=" * 60)
    print("Phase 9 Scenario 1: SO lifecycle + manufacturing delay + payment edge")
    print("=" * 60)
    
    # 1) List recent sales orders
    send("@ai list recent sales orders")
    
    # 2) Pick a specific SO and ask status
    send(f"@ai full status {so_name}")
    
    # 3) Introduce a manufacturing delay scenario
    send(f"@ai diagnose and fix {so_name} production delay")
    
    # 4) Ask workflow orchestrator to run full workflow
    send(f"@ai workflow run {so_name}")
    
    # 5) Simulate a partial payment / edge case
    send(f"@ai check payment status for {so_name}")
    send(f"@ai what is missing to fully pay {so_name}?")
    
    # 6) Wrap up summary - tests context memory
    send(f"@ai summarize what is blocking {so_name} right now")
    
    print("\n" + "=" * 60)
    print("Scenario complete!")
    print("=" * 60)
    
    return transcript


def main():
    """Entry point for CLI execution."""
    print("Starting Phase 9 Scenario...")
    print(f"User: {SITE_USER}")
    print(f"Channel: {CHANNEL_ID}")
    print()
    
    run_so_lifecycle_scenario(
        user=SITE_USER,
        channel_id=CHANNEL_ID
    )


if __name__ == "__main__":
    main()
