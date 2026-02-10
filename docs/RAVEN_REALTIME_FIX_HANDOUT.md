# Raven AI Agent - Real-time Messaging Fix

## Project Handout for Parallel Development

**Date:** 2026-02-10  
**Status:** Code fix complete, pending infrastructure verification  
**Priority:** High

---

## 1. Problem Statement

### Original Issue
AI-generated messages in the Frappe/Raven chat application were being saved to the database but **not appearing in the UI in real-time**. Users had to manually refresh the page to see AI responses.

### Error Message Observed
```
"Realtime events are not working. Please try refreshing the page."
```

---

## 2. Root Cause Analysis

### Investigation Summary

1. **Missing Real-time Events**: The original code was saving `Raven Message` documents but not publishing real-time events to notify the frontend.

2. **Incorrect Event Name**: Initial fix attempts used a guessed event name (`raven:message_created`) which was incorrect.

3. **Correct Implementation Found**: By analyzing the official Raven repository source code, we discovered:
   - **Correct event name:** `message_created`
   - **Required parameters:** `doctype="Raven Channel"`, `docname=channel_id`
   - **Payload structure:** Must include `message_details` object

4. **Infrastructure Issue**: The persistent "Realtime events not working" error is a **generic Socket.IO connection failure**, not a code logic problem. This indicates the websocket service itself may be down or misconfigured.

### Technical Details

#### How Frappe Real-time Works
- Frappe uses a Node.js-based Socket.IO server (`frappe-socketio`)
- Events are published to "rooms" (channels that clients subscribe to)
- Room naming convention: `doc:DocTypeName:DocName`
- Redis is used for pub/sub between Python backend and Node.js socket server

#### Frontend Subscription (from Raven source)
```typescript
// From raven/frontend/src/hooks/useChatStream.ts
useFrappeDocumentEventListener('Raven Channel', channelID, (event) => {
    if (event.event === 'message_created') {
        // Handle new message
    }
})
```

This subscribes to room: `doc:Raven Channel:<channel_id>`

#### Backend Publishing (correct implementation)
```python
frappe.publish_realtime(
    "message_created",
    {
        "channel_id": channel_id,
        "sender": frappe.session.user,
        "message_id": message_doc.name,
        "message_details": {...}  # Full message object
    },
    doctype="Raven Channel",
    docname=channel_id,
    after_commit=True
)
```

This publishes to room: `doc:Raven Channel:<channel_id>` ✓

---

## 3. Code Changes Made

### Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `api/channel_utils.py` | **NEW FUNCTION** | Added centralized `publish_message_created_event()` |
| `api/agent.py` | Modified | Replaced inline publish calls with utility function |
| `api/agent_V1.py` | Modified | Added message creation + publish event call |
| `channels/raven_channel.py` | Modified | Replaced inline publish call with utility function |

### New Utility Function

**File:** `/workspace/raven_ai_agent/api/channel_utils.py`

```python
def publish_message_created_event(message_doc, channel_id: str) -> None:
    """
    Publish a realtime event when a new Raven Message is created.
    This function centralizes the real-time event publishing logic to ensure
    consistency across all message creation points in the application.
    
    Args:
        message_doc: The Raven Message document that was created
        channel_id: The ID of the channel where the message was posted
    """
    frappe.publish_realtime(
        "message_created",
        {
            "channel_id": channel_id,
            "sender": frappe.session.user,
            "message_id": message_doc.name,
            "message_details": _get_message_details(message_doc),
        },
        doctype="Raven Channel",
        docname=channel_id,
        after_commit=True,
    )
```

### Usage Pattern

```python
from raven_ai_agent.api.channel_utils import publish_message_created_event

# After creating and saving a Raven Message document:
message_doc = frappe.get_doc({
    "doctype": "Raven Message",
    "channel_id": channel_id,
    "text": response_text,
    "message_type": "Text",
    # ... other fields
})
message_doc.insert(ignore_permissions=True)
frappe.db.commit()

# Publish the real-time event
publish_message_created_event(message_doc, channel_id)
```

---

## 4. Current Status

### ✅ Completed
- [x] Identified correct event name and parameters from Raven source
- [x] Created centralized utility function for publishing events
- [x] Refactored `api/agent.py` to use utility function
- [x] Refactored `api/agent_V1.py` to use utility function  
- [x] Refactored `channels/raven_channel.py` to use utility function
- [x] Verified all message creation points are covered

### ⏳ Pending (Infrastructure)
- [ ] Verify `frappe-socketio` service is running
- [ ] Verify Redis is operational
- [ ] Check nginx configuration for `/socket.io/` proxy
- [ ] Test on sandbox environment

---

## 5. Infrastructure Troubleshooting Guide

### Step 1: Check Service Status
```bash
cd /path/to/frappe-bench
bench status
```

Expected output should show all services running:
- `frappe-web` (Gunicorn workers)
- `frappe-socketio` (Node.js Socket.IO)
- `frappe-worker` (Background workers)
- `redis-cache`, `redis-queue`, `redis-socketio`

### Step 2: Check Socket.IO Logs
```bash
# If using supervisorctl
supervisorctl tail -f frappe-socketio

# Or check log files
tail -f /path/to/frappe-bench/logs/socketio.log
```

### Step 3: Verify Site Configuration
Check `sites/<site-name>/site_config.json`:
```json
{
    "socketio_port": 9000,
    "redis_socketio": "redis://localhost:11000"
}
```

### Step 4: Check Nginx Configuration
Ensure nginx has proper WebSocket proxy configuration:
```nginx
location /socket.io {
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header X-Frappe-Site-Name $host;
    proxy_set_header Host $host;
    proxy_pass http://127.0.0.1:9000;
}
```

### Step 5: Restart Services
```bash
bench restart
# Or specific service
supervisorctl restart frappe-socketio
```

### Step 6: Test WebSocket Connection
Open browser developer tools → Network tab → WS filter.
Look for connections to `/socket.io/` endpoint.

---

## 6. Key Files Reference

### Application Code
- `/workspace/raven_ai_agent/api/channel_utils.py` - Utility functions (includes publish event)
- `/workspace/raven_ai_agent/api/agent.py` - Main AI agent logic
- `/workspace/raven_ai_agent/api/agent_V1.py` - Legacy agent version
- `/workspace/raven_ai_agent/channels/raven_channel.py` - Channel communication

### Downloaded Reference Files (for analysis)
- `/workspace/extract/raven_message.py` - Official Raven message handling
- `/workspace/extract/raven_chat_stream.ts` - Frontend chat stream hook
- `/workspace/extract/raven_socket_connection.ts` - Frontend socket connection

### Documentation
- `/workspace/extract/raw_content/docs_frappe_io_*.txt` - Frappe realtime docs

---

## 7. Testing Checklist

### Unit Test (Code Logic)
1. Create a test Raven Message document
2. Call `publish_message_created_event()`
3. Verify no Python errors

### Integration Test (With Socket.IO)
1. Ensure `frappe-socketio` is running
2. Open Raven chat in browser
3. Send a message that triggers AI response
4. Verify AI response appears without page refresh
5. Check browser console for any WebSocket errors

### Debug Commands
```python
# In Frappe console, test publishing directly:
import frappe
frappe.publish_realtime(
    "message_created",
    {"test": "data"},
    doctype="Raven Channel", 
    docname="your-channel-id"
)
```

---

## 8. Contact & Context

### Original Issue Reporter
User experiencing real-time message delivery failures in production Raven deployment.

### Key Decisions Made
1. **Centralized utility function** - Chosen to ensure consistency and maintainability
2. **Match official Raven implementation** - Event name, parameters, and payload structure all match the official Raven repository
3. **`after_commit=True`** - Ensures event is published only after database transaction commits

### Known Limitations
- The code fix is complete but **cannot resolve infrastructure issues**
- If `frappe-socketio` is not running, real-time will not work regardless of code correctness
- Production testing should be done after sandbox verification

---

## 9. Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│ RAVEN REAL-TIME MESSAGING - QUICK REFERENCE                 │
├─────────────────────────────────────────────────────────────┤
│ Event Name:     message_created                             │
│ Room Format:    doc:Raven Channel:<channel_id>              │
│ Utility:        publish_message_created_event(doc, ch_id)   │
│ Location:       api/channel_utils.py                        │
├─────────────────────────────────────────────────────────────┤
│ Frontend Hook:  useFrappeDocumentEventListener              │
│ Backend Call:   frappe.publish_realtime()                   │
│ Required:       doctype="Raven Channel", docname=channel_id │
├─────────────────────────────────────────────────────────────┤
│ Services:       frappe-socketio (port 9000)                 │
│                 redis-socketio                              │
│ Check:          bench status                                │
│ Restart:        bench restart                               │
└─────────────────────────────────────────────────────────────┘
```

---

*Document created for parallel AI agent handoff. All code changes have been implemented and verified syntactically. Infrastructure verification pending.*
