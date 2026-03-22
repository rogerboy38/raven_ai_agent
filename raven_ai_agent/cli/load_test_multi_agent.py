"""
Phase 9 Load Test Script: Multi-Agent Concurrency Testing

This script tests the agent_bus and context_manager under concurrent load
to ensure they behave correctly when multiple agents are running simultaneously.

Usage:
    from raven_ai_agent.cli.load_test_multi_agent import run_load_test
    run_load_test(num_commands=100, num_users=10)
"""
import frappe
import time
import threading
import random
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from raven_ai_agent.api.router import handle_raven_message
from raven_ai_agent.utils.agent_bus import get_bus, AgentEvent, EVENT_SO_UPDATED
from raven_ai_agent.utils.context_manager import ContextStore


# Test commands that exercise different agents
TEST_COMMANDS = [
    "@ai list recent sales orders",
    "@ai status SO-00001",
    "@ai help",
    "@ai list open work orders",
    "@ai check payment status",
    "@ai list pending quotations",
]


class LoadTestMetrics:
    """Track load test results."""
    
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.events_published = 0
        self.context_updates = 0
        self.response_times: List[float] = []
        self.errors: List[str] = []
        self.lock = threading.Lock()
    
    def record_success(self, response_time: float):
        with self.lock:
            self.total_requests += 1
            self.successful_requests += 1
            self.response_times.append(response_time)
    
    def record_failure(self, error: str):
        with self.lock:
            self.total_requests += 1
            self.failed_requests += 1
            self.errors.append(error)
    
    def record_event(self):
        with self.lock:
            self.events_published += 1
    
    def record_context_update(self):
        with self.lock:
            self.context_updates += 1
    
    def get_summary(self) -> Dict:
        with self.lock:
            avg_response_time = (
                sum(self.response_times) / len(self.response_times)
                if self.response_times else 0
            )
            return {
                "total_requests": self.total_requests,
                "successful": self.successful_requests,
                "failed": self.failed_requests,
                "success_rate": self.successful_requests / self.total_requests if self.total_requests > 0 else 0,
                "avg_response_time_ms": avg_response_time * 1000,
                "events_published": self.events_published,
                "context_updates": self.context_updates,
                "error_count": len(self.errors),
            }


def send_test_command(
    user: str,
    channel: str,
    command: str,
    metrics: LoadTestMetrics,
    event_handler
) -> None:
    """Send a single command and record metrics."""
    start_time = time.time()
    
    try:
        # Subscribe to events to track them
        bus = get_bus()
        bus.subscribe(EVENT_SO_UPDATED, event_handler)
        
        # Send the command
        response = handle_raven_message(
            user=user,
            message=command,
            channel=channel,
        )
        
        # Record success
        response_time = time.time() - start_time
        metrics.record_success(response_time)
        
    except Exception as e:
        response_time = time.time() - start_time
        metrics.record_failure(str(e))
        print(f"Error: {e}")


def run_load_test(
    num_commands: int = 100,
    num_users: int = 10,
    channel: str = "Raven Load Test Channel"
) -> Dict:
    """
    Run load test with concurrent requests.
    
    Args:
        num_commands: Total number of commands to execute
        num_users: Number of concurrent users to simulate
        channel: Channel to send messages to
        
    Returns:
        Dictionary with test results and metrics
    """
    print("=" * 60)
    print(f"Starting Load Test: {num_commands} commands, {num_users} users")
    print("=" * 60)
    
    # Initialize metrics
    metrics = LoadTestMetrics()
    context_store = ContextStore()
    
    # Track published events
    published_events = []
    def event_tracker(event: AgentEvent):
        metrics.record_event()
        published_events.append(event)
    
    # Prepare tasks
    tasks = []
    for i in range(num_commands):
        user = f"loadtest_user{i % num_users}@example.com"
        command = random.choice(TEST_COMMANDS)
        tasks.append((user, command))
    
    # Run concurrent requests
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=num_users) as executor:
        futures = []
        for user, command in tasks:
            future = executor.submit(
                send_test_command,
                user,
                channel,
                command,
                metrics,
                event_tracker
            )
            futures.append(future)
        
        # Wait for all to complete
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                metrics.record_failure(str(e))
    
    total_time = time.time() - start_time
    
    # Get summary
    summary = metrics.get_summary()
    summary["total_time_seconds"] = total_time
    summary["requests_per_second"] = num_commands / total_time
    
    # Clean up event handlers
    bus = get_bus()
    bus.unsubscribe(EVENT_SO_UPDATED, event_tracker)
    
    # Print results
    print("\n" + "=" * 60)
    print("Load Test Results")
    print("=" * 60)
    print(f"Total Requests: {summary['total_requests']}")
    print(f"Successful: {summary['successful']}")
    print(f"Failed: {summary['failed']}")
    print(f"Success Rate: {summary['success_rate']*100:.1f}%")
    print(f"Avg Response Time: {summary['avg_response_time_ms']:.2f}ms")
    print(f"Events Published: {summary['events_published']}")
    print(f"Context Updates: {summary['context_updates']}")
    print(f"Total Time: {summary['total_time_seconds']:.2f}s")
    print(f"Requests/Second: {summary['requests_per_second']:.1f}")
    print("=" * 60)
    
    return summary


def main():
    """Entry point for CLI execution."""
    print("Starting Phase 9 Load Test...")
    
    # Run a moderate load test
    result = run_load_test(
        num_commands=50,
        num_users=5
    )
    
    # Check if test passed
    if result["success_rate"] >= 0.8:
        print("\n✓ Load test PASSED")
    else:
        print("\n✗ Load test FAILED - success rate below 80%")


if __name__ == "__main__":
    main()
