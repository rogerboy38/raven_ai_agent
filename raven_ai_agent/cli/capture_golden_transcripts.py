"""
Phase 9 Golden Transcript Capture Script

This script captures "golden transcripts" - expected conversation flows
that can be used for:
- Regression testing
- Documentation/examples
- Production runbooks

Usage:
    from raven_ai_agent.cli.capture_golden_transcripts import capture_transcript, save_transcript
    transcript = capture_transcript("sales_order_status")
    save_transcript(transcript, "golden_transcript_so_status.json")
"""
import json
import frappe
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from raven_ai_agent.api.router import handle_raven_message


# Define scenario templates
SCENARIOS = {
    "sales_order_status": {
        "description": "Check status of a specific Sales Order",
        "commands": [
            "@ai status SO-00001",
            "@ai what is the delivery status?",
        ]
    },
    "sales_order_list": {
        "description": "List recent sales orders",
        "commands": [
            "@ai list recent sales orders",
            "@ai show pending orders",
        ]
    },
    "manufacturing_work_order": {
        "description": "Create and manage work orders from SO",
        "commands": [
            "@ai create work order from SO-00001",
            "@ai list open work orders",
        ]
    },
    "payment_check": {
        "description": "Check payment status and create payments",
        "commands": [
            "@ai check payment status for SO-00001",
            "@ai show overdue invoices",
        ]
    },
    "full_workflow": {
        "description": "Run complete SO to invoice workflow",
        "commands": [
            "@ai workflow run SO-00001",
            "@ai full status SO-00001",
        ]
    },
}


def capture_transcript(
    scenario: str,
    user: str = "administrator@yourcompany.com",
    channel: str = "Raven Golden Transcript Channel",
    so_name: str = "SO-00001"
) -> Dict:
    """
    Capture a golden transcript for a given scenario.
    
    Args:
        scenario: Name of the scenario to capture
        user: User to run as
        channel: Channel to send to
        so_name: Sales Order to test with (replaces {so} placeholder)
        
    Returns:
        Dictionary with transcript and metadata
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}. Available: {list(SCENARIOS.keys())}")
    
    scenario_data = SCENARIOS[scenario]
    
    transcript = {
        "scenario": scenario,
        "description": scenario_data["description"],
        "captured_at": datetime.now().isoformat(),
        "user": user,
        "channel": channel,
        "so_name": so_name,
        "turns": []
    }
    
    def send(msg: str) -> str:
        """Send message and capture response."""
        # Replace placeholder
        msg = msg.replace("{so}", so_name)
        
        print(f"\n>> {user}: {msg}")
        try:
            response = handle_raven_message(
                user=user,
                message=msg,
                channel=channel,
            )
            print(f"<< Raven: {response[:200]}..." if len(str(response)) > 200 else f"<< Raven: {response}")
            
            transcript["turns"].append({
                "user_message": msg,
                "bot_response": response,
                "timestamp": datetime.now().isoformat()
            })
            
            return response
        except Exception as e:
            error_msg = str(e)
            print(f"<< ERROR: {error_msg}")
            
            transcript["turns"].append({
                "user_message": msg,
                "bot_response": f"ERROR: {error_msg}",
                "timestamp": datetime.now().isoformat(),
                "error": True
            })
            
            return error_msg
    
    print("=" * 60)
    print(f"Capturing Golden Transcript: {scenario}")
    print(f"Description: {scenario_data['description']}")
    print("=" * 60)
    
    # Execute each command in the scenario
    for command in scenario_data["commands"]:
        send(command)
    
    print("\n" + "=" * 60)
    print("Transcript capture complete!")
    print("=" * 60)
    
    return transcript


def save_transcript(
    transcript: Dict,
    filename: str,
    output_dir: str = "cli/golden_transcripts"
) -> str:
    """
    Save transcript to a JSON file.
    
    Args:
        transcript: The transcript dictionary
        filename: Output filename
        output_dir: Directory to save to
        
    Returns:
        Path to saved file
    """
    # Ensure output directory exists
    output_path = Path(output_dir) / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Add version info
    transcript["version"] = "1.0"
    
    # Save to file
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, indent=2, ensure_ascii=False)
    
    print(f"Transcript saved to: {output_path}")
    return str(output_path)


def load_transcript(filename: str) -> Dict:
    """
    Load a golden transcript from file.
    
    Args:
        filename: Path to transcript file
        
    Returns:
        The transcript dictionary
    """
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def compare_transcript(
    captured: Dict,
    golden: Dict,
    ignore_timestamps: bool = True
) -> Dict:
    """
    Compare a captured transcript with a golden transcript.
    
    Args:
        captured: The newly captured transcript
        golden: The golden reference transcript
        ignore_timestamps: Whether to ignore timestamp differences
        
    Returns:
        Comparison result with differences
    """
    differences = []
    
    # Compare turns
    if len(captured["turns"]) != len(golden["turns"]):
        differences.append({
            "type": "turn_count_mismatch",
            "captured": len(captured["turns"]),
            "golden": len(golden["turns"])
        })
    
    # Compare each turn
    for i, (c_turn, g_turn) in enumerate(zip(captured["turns"], golden["turns"])):
        if c_turn["user_message"] != g_turn["user_message"]:
            differences.append({
                "type": "message_mismatch",
                "turn": i,
                "captured": c_turn["user_message"],
                "golden": g_turn["user_message"]
            })
        
        # Check for errors in captured
        if c_turn.get("error") and not g_turn.get("error"):
            differences.append({
                "type": "unexpected_error",
                "turn": i,
                "error": c_turn["bot_response"]
            })
    
    return {
        "matches": len(differences) == 0,
        "differences": differences,
        "captured_turns": len(captured["turns"]),
        "golden_turns": len(golden["turns"])
    }


def main():
    """Entry point for CLI execution."""
    print("=" * 60)
    print("Golden Transcript Capture Tool")
    print("=" * 60)
    print(f"Available scenarios: {list(SCENARIOS.keys())}")
    print()
    
    # Capture each scenario
    for scenario_name in SCENARIOS.keys():
        print(f"\nCapturing: {scenario_name}")
        transcript = capture_transcript(scenario_name)
        
        # Save with scenario name
        filename = f"golden_transcript_{scenario_name}.json"
        save_transcript(transcript, filename)
    
    print("\n" + "=" * 60)
    print("All golden transcripts captured!")
    print("=" * 60)


if __name__ == "__main__":
    main()
