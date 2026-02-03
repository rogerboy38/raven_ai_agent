# Raven Channel Communication Specification

## Overview

This document proposes using **Raven channels** as the primary communication method between the Orchestrator Team (AI Agent) and the Implementation Team. This approach replaces the current markdown file-based communication with real-time, interactive messaging.

**Author:** Orchestrator Team (AI Agent)
**Date:** 2026-02-03
**Status:** 📋 PROPOSAL

---

## 1. Why Raven Channels?

### Current Approach (Markdown Files)
| Aspect | Current State |
|--------|---------------|
| Method | MD files in `docs/project_formulation/` |
| Speed | Slow (commit → review → commit) |
| Real-time | ❌ No |
| Notifications | ❌ Manual checking |
| Document Linking | ❌ Manual URLs |
| History | ✅ Git history |

### Proposed Approach (Raven Channels)
| Aspect | Proposed State |
|--------|----------------|
| Method | Raven channel messages |
| Speed | Fast (instant messaging) |
| Real-time | ✅ Yes |
| Notifications | ✅ Auto-push to channel |
| Document Linking | ✅ Native ERPNext links |
| History | ✅ Message history + Git backup |

---

## 2. Proposed Channel Architecture

### 2.1 Channel Structure

```
#formulation-orchestration (Private Channel)
├── @orchestrator-ai (AI Agent bot)
├── @implementation-team (Human developers)
└── @project-lead (You)
```

### 2.2 Channel Purpose

| Channel | Type | Purpose |
|---------|------|---------||
| `#formulation-orchestration` | Private | Main communication for phase specs |
| `#formulation-alerts` | Open | Automated notifications (tests, builds) |
| `#formulation-archive` | Private | Long-form documents backup |

---

## 3. Implementation Plan

### 3.1 Raven Bot Setup

Create a Raven Bot that the AI Agent can use to send messages:

```python
# raven_ai_agent/channels/raven_channel.py

import frappe
from raven.api.raven_message import send_message

class RavenOrchestrator:
    """Orchestrator communication via Raven channels."""
    
    def __init__(self, channel_name: str = "formulation-orchestration"):
        self.channel = frappe.get_doc("Raven Channel", channel_name)
    
    def send_spec(self, phase: int, content: str):
        """Send a phase specification to the channel."""
        message = f"""
## 📋 Phase {phase} Specification

{content}

---
*Sent by Orchestrator AI*
        """
        return send_message(
            channel_id=self.channel.name,
            text=message
        )
    
    def send_question(self, question: str, context: str = ""):
        """Ask a question to the implementation team."""
        message = f"""
## ❓ Question from Orchestrator

**Question:** {question}

{f"**Context:** {context}" if context else ""}

Please respond in this thread 👇
        """
        return send_message(
            channel_id=self.channel.name,
            text=message
        )
    
    def send_approval(self, phase: int, status: str, notes: str = ""):
        """Send phase approval/feedback."""
        emoji = "✅" if status == "approved" else "🔄"
        message = f"""
## {emoji} Phase {phase} Review

**Status:** {status.upper()}

{notes}
        """
        return send_message(
            channel_id=self.channel.name,
            text=message
        )
```

### 3.2 Message Templates

#### Phase Specification Message
```markdown
## 📋 Phase 2 Specification: BATCH_SELECTOR_AGENT

**Objective:** Intelligent batch selection for formulations

**Functions to implement:**
- `select_optimal_batches()`
- `calculate_blend_cost()`
- `validate_selection()`

**Linked Document:** [PHASE2_BATCH_SELECTOR_AGENT.md](/app/file-viewer/...)

---
*Click 👍 to acknowledge receipt*
```

#### Question Message
```markdown
## ❓ Question: Bin vs Batch AMB

Should we use `Bin` doctype for stock queries?

**Options:**
- 👍 Yes, use Bin
- 👎 No, use Batch AMB
- 💬 Need discussion

Reply in thread 👇
```

#### Test Report Message
```markdown
## 🧪 Test Report: Phase 1

| Suite | Tests | Status |
|-------|-------|--------|
| ParseGoldenNumber | 5 | ✅ |
| FEFOSorting | 2 | ✅ |
| ... | ... | ... |
| **TOTAL** | **32** | ✅ **ALL PASS** |

*Execution time: 0.446s*
```

---

## 4. Integration with Existing Workflow

### 4.1 Hybrid Approach

We recommend a **hybrid approach** combining both methods:

```
[Raven Channel]          [GitHub Repo]
      │                       │
      │    Specs/Questions    │
      ├──────────────────────►│  phase_X_chat.md (backup)
      │                       │
      │    Quick Q&A          │
      ◄─────────────────────── │  (no git needed)
      │                       │
      │    Reports/Tests      │
      ├──────────────────────►│  PHASE_X_REPORT.md
      │                       │
```

### 4.2 Workflow Steps

1. **Orchestrator sends spec** → Raven channel + MD file backup
2. **Team asks questions** → Raven thread (instant)
3. **Orchestrator answers** → Raven thread (instant)
4. **Team completes work** → Raven notification + MD report
5. **Orchestrator reviews** → Raven approval message

---

## 5. Required Setup

### 5.1 ERPNext Configuration

1. **Create Raven Channel:**
   - Name: `formulation-orchestration`
   - Type: Private
   - Members: Add project team

2. **Create Raven Bot:**
   - Name: `orchestrator-ai`
   - Permissions: Send messages to channel

3. **Configure Notifications:**
   - Enable desktop/mobile notifications for channel

### 5.2 Code Changes

```python
# Add to raven_ai_agent/channels/__init__.py
from .raven_channel import RavenOrchestrator

# Usage in skills
from raven_ai_agent.channels import RavenOrchestrator

orchestrator = RavenOrchestrator()
orchestrator.send_spec(phase=2, content="...")
```

---

## 6. Benefits Summary

| Benefit | Impact |
|---------|--------|
| **Faster Communication** | Questions answered in minutes vs hours |
| **Better Tracking** | All messages in one place with threads |
| **Native Integration** | Links to ERPNext documents work directly |
| **Notifications** | Team gets instant alerts |
| **Mobile Access** | Check updates from phone |
| **Audit Trail** | Full message history preserved |

---

## 7. Next Steps

- [ ] Create `#formulation-orchestration` channel in Raven
- [ ] Set up `orchestrator-ai` bot user
- [ ] Implement `RavenOrchestrator` class
- [ ] Test message sending from AI agent
- [ ] Migrate Phase 2 communication to Raven

---

## 8. Approval

| Role | Status | Notes |
|------|--------|-------|
| Project Lead | ⏳ PENDING | Needs approval to proceed |
| Implementation Team | ⏳ PENDING | Confirm channel setup |
| Orchestrator AI | ✅ APPROVED | Ready to implement |

---

*This proposal enhances our team communication while maintaining the documentation rigor of our current approach.*
