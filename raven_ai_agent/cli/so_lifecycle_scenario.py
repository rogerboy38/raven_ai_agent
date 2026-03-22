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
from raven_ai_agent.api.router import handle_raven_message


# Default configuration - adjust for your environment
SITE_USER = "administrator@yourcompany.com"  # change if needed
CHANNEL = "Raven Dev Channel"                # change if needed


def run_so_lifecycle_scenario(
    user: str = SITE_USER,
    channel: str = CHANNEL,
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
        channel: The channel to send messages to
        so_name: The Sales Order to test with
        
    Returns:
        List of (message, response) tuples for transcript capture
    """
    transcript = []
    
    def send(msg: str):
        """Send a message and capture the response."""
        print(f"\n>> {user}: {msg}")
        try:
            resp = handle_raven_message(
                user=user,
                message=msg,
                channel=channel,
            )
            print(f"<< Raven: {resp}")
            transcript.append((msg, resp))
            return resp
        except Exception as e:
            print(f"<< ERROR: {e}")
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
    print(f"Channel: {CHANNEL}")
    print()
    
    run_so_lifecycle_scenario(
        user=SITE_USER,
        channel=CHANNEL
    )


if __name__ == "__main__":
    main()
