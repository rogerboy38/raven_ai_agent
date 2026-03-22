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
from unittest.mock import MagicMock


# Default configuration - adjust for your environment
SITE_USER = "administrator@yourcompany.com"  # change if needed
CHANNEL_ID = "Raven Dev Channel"              # change if needed


def run_so_lifecycle_scenario(
    user: str = SITE_USER,
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
        so_name: The Sales Order to test with
        
    Returns:
        List of (message, response) tuples for transcript capture
    """
    transcript = []
    
    def send_to_agent(bot_type: str, msg: str) -> str:
        """Send message to appropriate agent and return response."""
        print(f"\n>> {user}: {msg}")
        try:
            if bot_type == "sales_order_follow_up":
                from raven_ai_agent.agents import SalesOrderFollowupAgent
                agent = SalesOrderFollowupAgent(user)
                response = agent.process_command(msg)
            elif bot_type == "manufacturing":
                from raven_ai_agent.agents import ManufacturingAgent
                agent = ManufacturingAgent()
                response = agent.process_command(msg)
            elif bot_type == "payment":
                from raven_ai_agent.agents import PaymentAgent
                agent = PaymentAgent()
                response = agent.process_command(msg)
            elif bot_type == "workflow_orchestrator":
                from raven_ai_agent.agents import WorkflowOrchestrator
                agent = WorkflowOrchestrator()
                response = agent.process_command(msg)
            else:
                response = f"Unknown bot type: {bot_type}"
            
            print(f"<< Raven: {response}")
            return response
        except Exception as e:
            error_msg = f"ERROR: {e}"
            print(f"<< {error_msg}")
            import traceback
            traceback.print_exc()
            return error_msg
    
    print("=" * 60)
    print("Phase 9 Scenario 1: SO lifecycle + manufacturing delay + payment edge")
    print("=" * 60)
    
    # 1) List recent sales orders
    response = send_to_agent("sales_order_follow_up", "list recent sales orders")
    transcript.append(("@ai list recent sales orders", response))
    
    # 2) Pick a specific SO and ask status
    response = send_to_agent("sales_order_follow_up", f"status {so_name}")
    transcript.append((f"@ai status {so_name}", response))
    
    # 3) Full status
    response = send_to_agent("sales_order_follow_up", f"full status {so_name}")
    transcript.append((f"@ai full status {so_name}", response))
    
    # 4) Manufacturing - list open work orders
    response = send_to_agent("manufacturing", "list open work orders")
    transcript.append(("@ai list open work orders", response))
    
    # 5) Payment - check payment status
    response = send_to_agent("payment", f"check payment status for {so_name}")
    transcript.append((f"@ai check payment status for {so_name}", response))
    
    # 6) Workflow orchestrator - run workflow
    response = send_to_agent("workflow_orchestrator", f"run {so_name}")
    transcript.append((f"@ai workflow run {so_name}", response))
    
    print("\n" + "=" * 60)
    print("Scenario complete!")
    print("=" * 60)
    
    return transcript


def main():
    """Entry point for CLI execution."""
    print("Starting Phase 9 Scenario...")
    print(f"User: {SITE_USER}")
    print()
    
    run_so_lifecycle_scenario(
        user=SITE_USER
    )


if __name__ == "__main__":
    main()
