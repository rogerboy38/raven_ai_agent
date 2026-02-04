# Phase 6: Report Generator - Quick Reference Guide

## 📋 Available Actions

### 1. Production Order Report
**Action:** `production_order_report`  
**Purpose:** Generate picking lists for manufacturing

```python
action="production_order_report"
payload={
    "workflow_state": {
        "request": {...},
        "phases": {"optimization": {"selected_batches": [...]}}
    }
}
```

### 2. Cost Report
**Action:** `cost_report`  
**Purpose:** Financial analysis with cost breakdown

```python
action="cost_report"
payload={
    "workflow_state": {
        "phases": {"costs": {"total_cost": ..., "currency": "MXN"}}
    },
    "report_type": "cost"
}
```

### 3. Compliance Report
**Action:** `compliance_report`  
**Purpose:** FEFO and TDS compliance verification

```python
action="compliance_report"
payload={
    "workflow_state": {
        "phases": {"compliance": {"passed": ..., "compliant_batches": ...}}
    },
    "report_type": "compliance"
}
```

### 4. Summary Report
**Action:** `summary_report`  
**Purpose:** Executive overview with recommendations

```python
action="summary_report"
payload={
    "workflow_state": {
        "request": {...},
        "phases": {"batch_selection": ..., "compliance": ..., "costs": ...}
    },
    "report_type": "summary"
}
```

### 5. Format as ASCII
**Action:** `format_as_ascii`  
**Purpose:** Convert any report to ASCII table

```python
action="format_as_ascii"
payload={
    "report": {...}  # Any report dictionary
}
```

### 6. Format for Raven
**Action:** `format_for_raven`  
**Purpose:** Generate Raven-friendly markdown

```python
action="format_for_raven"
payload={
    "report": {...}  # Any report dictionary
}
```

### 7. Save to ERPNext
**Action:** `save_to_erpnext`  
**Purpose:** Create Note document in ERPNext

```python
action="save_to_erpnext"
payload={
    "report": {...},
    "title": "Report Title",  # Optional
    "public": False  # Optional
}
```

### 8. Email Report
**Action:** `email_report`  
**Purpose:** Email report to recipients

```python
action="email_report"
payload={
    "report": {...},
    "recipients": ["user@example.com"],
    "subject": "Report Subject",  # Optional
    "cc": ["manager@example.com"]  # Optional
}
```

---

## 📊 Report Type Decision Tree

```
Need a report?
│
├─ For manufacturing/production? → production_order_report
│   └─ Get: Picking list with batch sequence, warehouse, quantities
│
├─ For financial review? → cost_report
│   └─ Get: Total cost, per-batch breakdown, strategy comparison
│
├─ For compliance audit? → compliance_report
│   └─ Get: FEFO/TDS status, violations, compliance details
│
└─ For executive overview? → summary_report
    └─ Get: Key metrics, compliance status, recommendations
```

---

## 🔄 Output Format Options

| Format | When to Use | Example |
|--------|-------------|---------|
| **dict** (default) | Programmatic access, JSON API responses | `{"report_type": "summary", ...}` |
| **ascii** | Terminal display, logs, text-based systems | Fixed-width table with borders |
| **markdown** | Raven chat, documentation, web display | Tables, emojis, formatted text |

---

## 🧪 Quick Test Examples

### Test 1: Generate All Report Types
```python
from raven_ai_agent.skills.formulation_orchestrator.agents import ReportGenerator
from raven_ai_agent.skills.formulation_orchestrator.messages import AgentMessage

agent = ReportGenerator()

# Test data
workflow_state = {
    "workflow_id": "test_001",
    "request": {"item_code": "TEST-ITEM", "quantity_required": 100},
    "phases": {
        "optimization": {
            "selected_batches": [
                {"batch_name": "B001", "quantity_to_use": 50, "warehouse": "WH1", "expiry_date": "2027-01-01"}
            ]
        },
        "costs": {"total_cost": 1000, "currency": "MXN"},
        "compliance": {"passed": True, "compliant_count": 1}
    }
}

# Test all report types
for action in ["production_order_report", "cost_report", "compliance_report", "summary_report"]:
    msg = AgentMessage(
        source_agent="test",
        target_agent="report_generator",
        action=action,
        payload={"workflow_state": workflow_state}
    )
    response = agent.handle_message(msg)
    assert response.success
    print(f"✅ {action}: {response.result['report_type']}")
```

### Test 2: ASCII Formatting
```python
# Generate report
report = agent.handle_message(AgentMessage(
    source_agent="test",
    target_agent="report_generator",
    action="production_order_report",
    payload={"workflow_state": workflow_state}
)).result

# Format as ASCII
ascii_msg = AgentMessage(
    source_agent="test",
    target_agent="report_generator",
    action="format_as_ascii",
    payload={"report": report}
)
ascii_response = agent.handle_message(ascii_msg)
print(ascii_response.result['ascii_output'])
```

### Test 3: ERPNext Integration (Mock)
```python
from unittest.mock import Mock, patch

with patch('raven_ai_agent.skills.formulation_orchestrator.agents.report_generator.frappe') as mock_frappe:
    # Mock Note creation
    mock_note = Mock()
    mock_note.name = "NOTE-001"
    mock_frappe.get_doc.return_value = mock_note
    mock_frappe.utils.get_url_to_form.return_value = "http://example.com/note/NOTE-001"
    
    # Save to ERPNext
    save_msg = AgentMessage(
        source_agent="test",
        target_agent="report_generator",
        action="save_to_erpnext",
        payload={"report": report, "title": "Test Report"}
    )
    save_response = agent.handle_message(save_msg)
    
    assert save_response.success
    assert save_response.result['note_name'] == "NOTE-001"
    print(f"✅ Saved as: {save_response.result['note_name']}")
```

---

## 🐛 Common Issues & Solutions

### Issue 1: Missing optimization data
**Error:** Empty picking_instructions list  
**Solution:** Ensure `workflow_state.phases.optimization.selected_batches` is populated

### Issue 2: Email fails silently
**Error:** `success: False, error: "No recipients specified"`  
**Solution:** Always provide `recipients` list in payload

### Issue 3: ASCII formatting broken
**Error:** Columns misaligned  
**Solution:** Check that batch IDs don't exceed 20 characters (or adjust column width)

### Issue 4: Note creation fails
**Error:** `frappe.exceptions.ValidationError`  
**Solution:** Ensure frappe is properly initialized and user has Note creation permissions

---

## 📝 Checklist for Integration

- [ ] Phase 5 outputs `selected_batches` list
- [ ] Batches include `batch_name`, `quantity_to_use`, `warehouse`, `expiry_date`
- [ ] Cost data includes `total_cost` and `currency`
- [ ] Compliance data includes `passed` flag and batch lists
- [ ] Frappe environment initialized for ERPNext integration
- [ ] Email recipients configured if using email action
- [ ] Tests passing (RPT-001 through RPT-012)

---

## 🔗 Related Files

- **Implementation:** `raven_ai_agent/skills/formulation_orchestrator/agents/report_generator.py`
- **Tests:** `raven_ai_agent/skills/formulation_orchestrator/tests.py`
- **Full Spec:** `docs/project_formulation/PHASE6_REPORT_GENERATOR.md`
- **Implementation Doc:** `docs/project_formulation/PHASE6_IMPLEMENTATION_COMPLETE.md`

---

**Last Updated:** February 5, 2026  
**Status:** ✅ Implementation Complete
