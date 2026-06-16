# `hooks.py` Patch — wire `crm_agent` into the Frappe app

Add (or merge) the following blocks into `raven_ai_agent/hooks.py`.

## 1. DocType events

```python
doc_events = {
    # ... your existing events ...
    "Lead": {
        "after_insert":
            "raven_ai_agent.skills.crm_agent.agents.lead_enricher.on_lead_after_insert",
    },
    "Opportunity": {
        "on_update":
            "raven_ai_agent.skills.crm_agent.agents.opportunity_mover.on_opportunity_update",
    },
    "Communication": {
        "after_insert":
            "raven_ai_agent.skills.crm_agent.agents.meeting_capturer.on_communication_after_insert",
    },
}
```

## 2. Scheduler

```python
scheduler_events = {
    "daily": [
        # ... existing ...
        "raven_ai_agent.skills.crm_agent.agents.pipeline_summarizer.run_daily_digest",
    ],
    "hourly": [
        # ... existing ...
        "raven_ai_agent.skills.crm_agent.agents.opportunity_mover.scan_stalled_opportunities",
    ],
}
```

## 3. AI Agent Settings — new fields

Append to `raven_ai_agent/config/doctype_fields.py` `NEW_FIELDS`:

```python
# --- CRM Agent ---
{"fieldname": "crm_section", "fieldtype": "Section Break", "label": "CRM Agent"},
{
    "fieldname": "crm_autonomy_level",
    "fieldtype": "Int",
    "label": "CRM Autonomy Level",
    "default": 1,
    "description": "0=observe, 1=suggest, 2=draft, 3=act, 4=autonomous",
},
{
    "fieldname": "crm_digest_channel",
    "fieldtype": "Link",
    "options": "Raven Channel",
    "label": "CRM Digest Channel",
},
{
    "fieldname": "crm_default_pipeline",
    "fieldtype": "Data",
    "label": "CRM Default Pipeline",
    "default": "Sales",
},
{
    "fieldname": "crm_followup_language",
    "fieldtype": "Select",
    "options": "auto\nen\nes",
    "label": "Follow-up Language",
    "default": "auto",
},
```

Run after merging:

```bash
bench --site <site> migrate
bench --site <site> execute raven_ai_agent.api.custom_fields.create_custom_fields
bench --site <site> clear-cache
bench restart
```

## 4. (Optional) Register in `ai_skill_registry`

If you keep a singleton `AI Skill Registry` doctype row per skill, add:

```python
# patches/v0_2/__init__.py
import frappe

def execute():
    if not frappe.db.exists("AI Skill Registry", "crm_agent"):
        frappe.get_doc({
            "doctype": "AI Skill Registry",
            "skill": "crm_agent",
            "enabled": 1,
            "category": "crm",
            "priority": 65,
        }).insert(ignore_permissions=True)
```

And add the patch path to `patches.txt`:

```
raven_ai_agent.patches.v0_2.register_crm_agent
```
