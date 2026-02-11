# Frappe Cloud Isolation Test - Minimal Hooks

## Problem Identified

The `raven_ai_agent` app has a `doc_events` hook that fires on **every Raven Message**:

```python
# hooks.py (CURRENT)
doc_events = {
    "Raven Message": {
        "after_insert": "raven_ai_agent.api.agent.handle_raven_message"
    }
}
```

This hook:
1. Runs synchronously on message insert
2. May cause import errors (python-socketio not installed)
3. May interfere with Frappe's realtime event cycle

## Solution: Disable Hooks for Testing

### Step 1: On the fresh Frappe Cloud bench, BEFORE installing raven_ai_agent

Create a test version of hooks.py that disables all doc_events:

```python
# hooks.py (MINIMAL VERSION)
app_name = "raven_ai_agent"
app_title = "Raven AI Agent"
app_publisher = "Your Company"
app_description = "AI Agent for ERPNext"
app_email = "your@email.com"
app_license = "MIT"
required_apps = ["frappe"]

# DISABLED FOR TESTING - doc_events hook suspected of causing Socket.IO issues
# doc_events = {
#     "Raven Message": {
#         "after_insert": "raven_ai_agent.api.agent.handle_raven_message"
#     }
# }

# DISABLED FOR TESTING
# scheduler_events = {
#     "daily": [
#         "raven_ai_agent.utils.memory.generate_daily_summaries"
#     ]
# }

website_route_rules = []
fixtures = ["AI Agent Settings"]
```

### Step 2: Test Installation

```bash
# On Frappe Cloud bench
cd ~/frappe-bench
bench get-app raven_ai_agent https://github.com/rogerboy38/raven_ai_agent.git

# BEFORE installing, edit hooks.py to disable doc_events
nano apps/raven_ai_agent/raven_ai_agent/hooks.py
# Comment out doc_events and scheduler_events

# Now install
bench --site sysmayal.v.frappe.cloud install-app raven_ai_agent
bench --site sysmayal.v.frappe.cloud migrate
bench restart
```

### Step 3: Test Socket.IO

1. Go to Raven
2. Check if "Realtime events are not working" banner appears
3. Test native bot messaging

### Step 4: Report Results

| Scenario | Socket.IO Status |
|----------|------------------|
| Fresh bench (no raven_ai_agent) | ✅ Working |
| With raven_ai_agent (hooks DISABLED) | ? |
| With raven_ai_agent (hooks ENABLED) | ? |

If Socket.IO works with hooks disabled but breaks with hooks enabled,
**the doc_events hook is confirmed as the root cause**.

## Long-term Fix

If the doc_events hook is the culprit, we need to:

1. Make the hook async (use frappe.enqueue instead of synchronous execution)
2. Add error handling to prevent import failures
3. Ensure the hook doesn't block the Frappe realtime event pipeline

### Async Hook Example:

```python
# hooks.py (FIXED)
doc_events = {
    "Raven Message": {
        "after_insert": "raven_ai_agent.api.agent.handle_raven_message_async"
    }
}
```

```python
# api/agent.py
def handle_raven_message_async(doc, method):
    """Non-blocking hook - enqueues processing"""
    # Quick checks synchronously
    if doc.is_bot_message or not doc.text:
        return
    
    # Check for @ai trigger
    plain_text = BeautifulSoup(doc.text, "html.parser").get_text().strip()
    if not any(trigger in plain_text.lower() for trigger in ["@ai", "@sales_order_bot", "@rnd_bot", "@executive"]):
        return
    
    # Enqueue heavy processing (async)
    frappe.enqueue(
        "raven_ai_agent.api.agent.process_raven_message_background",
        doc_name=doc.name,
        queue="default",
        timeout=300
    )
```

This ensures:
- The hook returns immediately (doesn't block Frappe)
- AI processing happens in background
- Socket.IO events fire normally
