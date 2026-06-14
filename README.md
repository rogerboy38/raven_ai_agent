# Raven AI Agent

Raymond-Lucy AI Agent for ERPNext with Raven Integration - Enhanced with OpenClaw-inspired architecture.

## Current Status

**Latest Update:** June 2026 | **Version:** 2.1 · skill `crm-agent` v0.1.1 · patterns v0.1.0
**Production Deployment:** Active on https://erp.sysmayal2.cloud
**Cleanup branch:** [`crm-V14.1.1`](https://github.com/rogerboy38/raven_ai_agent/tree/crm-V14.1.1) (PR [#17](https://github.com/rogerboy38/raven_ai_agent/pull/17), [#18](https://github.com/rogerboy38/raven_ai_agent/pull/18))

### Recent Deployments

| Date | Changes |
|------|---------|
| 2026-06-14 | **CRM Agent skill v0.1.1** (B/M/S/N cleanup pass) + **raven_ai_agent_patterns v0.1.0** (guardrails / planner helpers). 6 CRM custom fields on AI Agent Settings, kebab-case skill name `crm-agent`, full bilingual (EN/ES) intent coverage. Verified on `v2.sysmayal.cloud`: 43/43 tests, migrate exit 0, hooks resolve, idempotent re-run. |
| 2026-03-21 | Pipeline diagnosis commands (@ai pipeline, @ai diagnose), Payment Agent, Manufacturing workflow |
| 2026-03-20 | Data Quality Scanner, Sample Request from Lead/Prospect/Opportunity/Quotation/SO |
| 2026-03-19 | Payment Entry creation and submission fixes, @ai payment routing |
| 2026-03-09 | Sales Invoice workflow fixes (mode_of_payment field), command routing corrections |
| 2026-03-09 | Quality Management System (QMS) field bug fixes |
| 2026-03-08 | Raven User synchronization for mobile/web parity |
| 2026-03-08 | Phase 4 Advanced Analytics & Reporting module initiated |

## Features

### Core Protocols

- **Raymond Protocol**: Anti-hallucination with verified ERPNext data
- **Memento Protocol**: Persistent memory storage across sessions
- **Lucy Protocol**: Context continuity with morning briefings
- **Karpathy Protocol**: Autonomy slider (Copilot → Command → Agent)

### Multi-Provider LLM Support

| Provider | Models | Features |
|----------|--------|----------|
| **OpenAI** | gpt-4o, gpt-4o-mini, gpt-4-turbo | Default provider |
| **DeepSeek** | deepseek-chat, deepseek-reasoner | Cost-effective, reasoning mode |
| **Claude** | claude-3-5-sonnet, claude-3-opus | Strong analysis |
| **MiniMax** | abab6.5-chat, abab5.5-chat | Multilingual |

### Multi-Channel Gateway

- **Raven (Primary)**: Native ERPNext chat integration with AI commands
- **WhatsApp Business API**: Full messaging + interactive buttons
- **Telegram Bot**: Messages, voice, inline keyboards
- **Slack**: Direct messages, app mentions, button actions
- **Session Management**: Cross-channel context preservation

### Voice Integration

- **ElevenLabs TTS**: Text-to-speech responses
- **Multiple Voices**: Rachel, Drew, Bella, and more
- **Auto Voice Detection**: Respond with voice when appropriate

### Skills Platform

- **Browser Control**: Web automation and data extraction
- **Extensible Architecture**: Easy to add new skills
- **Intent Routing**: Automatic skill matching

### Quality Management System (QMS)

The QMS module provides comprehensive quality control capabilities through Raven AI commands:

| Command | Description |
|---------|-------------|
| `@ai quality setup status` | View QMS configuration and status |
| `@ai quality create nc <subject>` | Create Non-Conformance report |
| `@ai quality create training <name>` | Create Training Program |
| `@ai quality create audit <subject>` | Create Internal Audit |

**Verified Working (March 2026):**
- ✅ Non-Conformance Creation: QA-NC-00020
- ✅ Internal Audit Creation: QA-MEET-26-03-08
- ✅ Training Program Creation: GMP Basics

### Pipeline & Diagnosis Commands

Full sales pipeline management from Quotation to Delivery:

| Command | Description |
|---------|-------------|
| `@ai pipeline SAL-QTN-XXXX` | Full pipeline diagnosis with status |
| `@ai diagnose SAL-QTN-XXXX` | Detailed diagnosis with issues and next steps |
| `@ai check data SAL-QTN-XXXX` | Validate quotation data quality |
| `@ai fix SAL-QTN-XXXX` | Auto-fix data quality issues |
| `@ai scan SAL-QTN-XXXX` | Full data quality scan |
| `@ai validate SAL-QTN-XXXX` | Validate data integrity |
| `@ai repair SAL-QTN-XXXX` | Auto-repair issues |
| `@ai validate ACC-SINV-XXXXX` | Validate sales invoice |
| `@ai !fix SAL-QTN-XXXXX` | Fix cancelled quotation |
| `@ai !update quotation SAL-QTN-XXXX item ITEM-CODE` | Update quotation item |

**Pipeline Stages:**
- Quotation → Sales Order → Work Order → Stock Entry → Delivery Note → Sales Invoice → Payment

### Sales-to-Purchase Full Cycle

Complete sales pipeline from opportunity to payment and purchase requisition:

#### Sales Cycle
| Command | Description |
|---------|-------------|
| `@ai show opportunities` | List sales opportunities |
| `@ai create opportunity for [customer]` | Create new sales opportunity |
| `@ai check inventory for [SO]` | Check item availability for Sales Order |
| `@ai show quotations` | View your quotations |
| `@ai show sales orders` | View your sales orders |
| `@ai show pending deliveries` | Delivery notes, stock levels |
| `@ai create delivery note for [SO]` | Ship items to customer |
| `@ai create sales invoice for [SO/DN]` | Invoice the customer |

#### Purchase Cycle
| Command | Description |
|---------|-------------|
| `@ai create material request for [SO]` | Create Material Request from SO |
| `@ai show material requests` | List pending material requests |
| `@ai create rfq from [MR]` | Create Request for Quotation |
| `@ai show rfqs` | List RFQs and their status |
| `@ai show supplier quotations` | List supplier quotations |
| `@ai create po from [SQ]` | Create Purchase Order from Supplier Quotation |
| `@ai receive goods for [PO]` | Create Purchase Receipt |

### Payment Management Agent

Complete payment workflow automation:

| Command | Description |
|---------|-------------|
| `@ai payment create [SI-NAME]` | Create Payment Entry from Sales Invoice |
| `@ai payment create [SI-NAME] amount [AMOUNT]` | Partial payment |
| `@ai payment submit [PE-NAME]` | Submit Payment Entry |
| `@ai payment reconcile [PE-NAME]` | Check reconciliation status |
| `@ai payment outstanding` | List all unpaid invoices |
| `@ai payment outstanding customer [NAME]` | Unpaid for specific customer |
| `@ai payment status [PE-NAME]` | Payment Entry details |
| `@ai create payment for ACC-SINV-XXXX` | Create Payment Entry from Sales Invoice |
| `@ai validate ACC-SINV-XXXX` | Validate sales invoice |

**Full Payment Cycle:**
```
@ai payment create ACC-SINV-2026-00001
@ai payment submit ACC-PAY-2026-00001
@ai payment reconcile ACC-PAY-2026-00001
```

### Manufacturing Workflow Agent

Automated manufacturing from Sales Order:

| Command | Description |
|---------|-------------|
| `@ai work order from SO-XXXXX` | Create Work Order from Sales Order |
| `@ai transfer materials` | Transfer raw materials to WIP |
| `@ai manufacture MFG-WO-XXXXX` | Complete manufacturing |
| `@ai submit wo MFG-WO-XXXXX` | Submit Work Order |
| `@ai !submit Work Order MFG-WO-XXXX` | Submit Work Order (direct) |
| `@ai !submit bom BOM-XXXX` | Submit Bill of Materials |
| `@ai unlink sales order from MFG-WO-XXXX` | Remove SO link from Work Order |
| `@ai !cancel bom BOM-XXXX` | Cancel submitted BOM |
| `@ai !revert bom BOM-XXXX to draft` | Reset cancelled BOM to draft |

### Sample Request Management

Create Sample Requests from any source document via button or command:

| Command | Description |
|---------|-------------|
| `Create → Sample Request` button | Lead, Prospect, Opportunity, Quotation, Sales Order |
| `@ai sample request Lead LEAD-NAME` | Create sample request from Lead |
| `@ai sample request Prospect PROSPECT-NAME` | Create sample request from Prospect |
| `@ai sample request Opportunity OPP-NAME` | Create sample request from Opportunity |
| `@ai sample request Quotation SAL-QTN-XXXX` | Create sample request from Quotation |
| `@ai sample request Sales Order SO-XXXX` | Create sample request from Sales Order |

**Features:**
- Auto-populates party, contact, address
- Default item selection based on source type
- Request type mapping: Marketing, Prospect, Pre-sample Approved, Representative Sample, Exhibition

### Data Quality Scanner

Pre-flight validation and repair:

| Command | Description |
|---------|-------------|
| `@ai scan SAL-QTN-XXXX` | Full data quality scan |
| `@ai validate SAL-QTN-XXXX` | Validate data integrity |
| `@ai repair SAL-QTN-XXXX` | Auto-repair issues |

### Cost Monitoring

- **Usage Tracking**: Per-user token consumption
- **Budget Alerts**: Warnings when approaching limits

## Comparison: raven_ai_agent vs OpenClaw

| Feature | raven_ai_agent | OpenClaw |
|---------|---------------|----------|
| **Integration** | Frappe/Raven + Multi-channel | Multi-channel only |
| **Architecture** | Gateway + Session Management | Gateway/WebSocket |
| **AI Backend** | OpenAI + DeepSeek + Claude + MiniMax | Claude + OpenAI + local |
| **Channels** | Raven, WhatsApp, Telegram, Slack | WhatsApp, Telegram, Slack |
| **Voice** | ElevenLabs TTS | ElevenLabs |
| **Skills** | Browser control, extensible | Browser, canvas, device |
| **Cost Monitor** | ✅ Built-in | ❌ |
| **ERPNext Native** | ✅ | ❌ |

## Installation

```bash
bench get-app https://github.com/your-repo/raven_ai_agent
bench --site your-site install-app raven_ai_agent
```

## Configuration

### AI Agent Settings

1. Go to **AI Agent Settings** in ERPNext
2. Select **Default Provider** and enter API keys
3. Set **Fallback Provider** for automatic failover
4. Configure **Cost Budget** for usage warnings

### Channel Configuration (Optional)

```python
# WhatsApp
whatsapp_config = {
    "phone_number_id": "YOUR_ID",
    "access_token": "YOUR_TOKEN",
    "verify_token": "YOUR_VERIFY_TOKEN"
}

# Telegram
telegram_config = {"bot_token": "YOUR_BOT_TOKEN"}

# Slack  
slack_config = {
    "bot_token": "xoxb-YOUR-TOKEN",
    "signing_secret": "YOUR_SECRET"
}
```

### Voice Configuration (Optional)

```python
voice_config = {
    "elevenlabs_api_key": "YOUR_KEY",
    "default_voice": "rachel"
}
```

## Usage

### In Raven

```
@ai What are my pending sales invoices?
@ai Show me top customers by revenue
@ai quality setup status
@ai !quality create training GMP Basics
```

### Via API

```python
from raven_ai_agent.api.agent_v2 import process_message_v2

result = process_message_v2("What invoices are due?")
result = process_message_v2("Analyze data", provider="claude")
```

### Multi-Channel

```python
from raven_ai_agent.channels import get_channel_adapter
from raven_ai_agent.gateway import session_manager

adapter = get_channel_adapter("whatsapp", config)
incoming = adapter.parse_webhook(payload)
session = session_manager.get_or_create_session(user_id, "whatsapp", incoming.channel_user_id)
```

### Voice

```python
from raven_ai_agent.voice import ElevenLabsVoice

tts = ElevenLabsVoice(api_key="YOUR_KEY")
audio = tts.text_to_speech("Hello!")
```

## Autonomy Levels

| Level | Name | Description |
|-------|------|-------------|
| 1 | Copilot | Read-only queries, suggestions |
| 2 | Command | Execute with confirmation (use `!` prefix) |
| 3 | Agent | Multi-step autonomous workflows |

**Important:** Commands with `!` prefix execute directly without confirmation. Always use `@ai !command` format in Raven channels.

## Architecture

```
raven_ai_agent/
├── api/
│   ├── agent.py           # V1 API
│   ├── agent_v2.py        # V2 API (Multi-provider)
│   ├── workflows.py       # Business workflow automation
│   └── command_router.py  # Command routing logic
├── handlers/
│   └── quality_management.py  # QMS command handlers
├── providers/             # LLM Providers
│   ├── openai_provider.py
│   ├── deepseek.py
│   ├── claude.py
│   └── minimax.py
├── gateway/               # Multi-channel control
│   ├── session_manager.py
│   └── router.py
├── channels/              # Channel adapters
│   ├── whatsapp.py
│   ├── telegram.py
│   └── slack.py
├── voice/                 # Voice integration
│   └── elevenlabs.py
├── skills/                # Extensible skills
│   └── browser.py
└── utils/
    ├── memory.py
    └── cost_monitor.py
```

## Phase 4: Advanced Analytics & Reporting Module

**Status:** In Development (March 2026)

### Planned Features

| Feature | Description |
|---------|-------------|
| Dashboard Widgets | Custom analytics widgets for Raven |
| Smart Aggregations | AI-powered data summarization |
| Scheduled Reports | Automated report generation and distribution |
| Alert Rules Engine | Configurable business alerts |

## Formulation Orchestrator

Intelligent batch selection and formulation optimization for perishable inventory management in manufacturing environments.

### Overview

The Formulation Orchestrator is a multi-agent system designed to optimize batch selection for production orders, balancing FEFO (First Expiry, First Out) compliance with cost efficiency.

### Agent Architecture

| Phase | Agent | Purpose |
|-------|-------|----------|
| 1 | **Formulation Reader** | Parse and validate formulation data from ERPNext BOMs |
| 2 | **Batch Selector** | Query and filter available inventory batches |
| 3 | **TDS Compliance Checker** | Verify Technical Data Sheet requirements |
| 4 | **Cost Calculator** | Analyze batch costs and valuation methods |
| 5 | **Optimization Engine** | Multi-strategy batch selection optimization |
| 6 | **Report Generator** | Production-ready output formatting |

### Optimization Strategies

- **FEFO Cost Balanced** (Default): Hybrid approach balancing expiry dates with cost optimization
- **Minimize Cost**: Pure cost optimization for budget-conscious selections
- **Strict FEFO**: Guarantees full FEFO compliance
- **Minimum Batches**: Reduces picking complexity by minimizing batch count

### Key Features

- **What-If Scenarios**: Compare all strategies before committing to a selection
- **Constraint Satisfaction**: Shelf life requirements, warehouse filters, batch exclusions
- **Cost Integration**: Leverages Phase 4 cost trends for intelligent weighting
- **FEFO Violation Detection**: Automatic tracking and reporting

### Documentation

Complete project documentation is available in `docs/project_formulation/`:
- Phase implementation reports
- Technical specifications
- Agent communication protocols
- Unit test specifications

## CRM Agent Skill (v0.1.1)

Agentic CRM for ERPNext — humans supervise agents that enrich leads, advance opportunities, draft follow-ups, and summarize pipeline. Inspired by the "humans supervise agents" model but built on Frappe-native DocTypes (`Lead`, `Opportunity`, `Contact`, `Customer`, `Communication`, `Quotation`) and the existing `raven_ai_agent` skill framework.

Full skill manifest: [`raven_ai_agent/skills/crm_agent/SKILL.md`](raven_ai_agent/skills/crm_agent/SKILL.md)

### What's new in v0.1.1 (cleanup pass)

| Tier | Item | Resolution |
|------|------|------------|
| **B1** | Patterns module missing | Shipped `raven_ai_agent_patterns` v0.1.0 (guardrails + planner) |
| **M1** | Skill name inconsistency | Canonical kebab-case `crm-agent` everywhere (was mixed snake/kebab) |
| **M2** | Class name mismatch | `CRMAgentSkill` (uppercase RM) consistent across imports + `__init__.py` |
| **M3** | Currency hard-coded | `_default_currency()` resolves Company default → Global Defaults → MXN fallback |
| **M4** | Bare `$` in templates | Currency-aware formatter; never emits naked `$` |
| **M5** | Registry rename (snake→kebab) | Patch ships guarded by `frappe.db.exists()` — N/A on v1.0.0 (no `AI Skill Registry` DocType yet) |
| **S1–S6** | Test gaps, regex coverage, ES intent parity | Added autonomy enforcement, hook entrypoint, audit-call tests (43 total) |
| **N1–N7** | Linting, docstrings, import order | Cleaned up |

### `@ai` commands (bilingual EN / ES)

| Intent | Example (EN) | Example (ES) |
|--------|--------------|--------------|
| Daily pipeline digest | `@ai morning brief` | `@ai resumen del día` |
| List pipeline | `@ai show pipeline this week` | `@ai muéstrame el pipeline de esta semana` |
| Next best action | `@ai next step Opp-0042` | `@ai qué sigue con Opp-0042` |
| Draft follow-up | `@ai draft follow-up for Opp-0042` | `@ai redacta seguimiento para Opp-0042` |
| Move stage | `@ai move Opp-0042 to Quotation` | `@ai mueve Opp-0042 a Cotización` |
| Enrich lead | `@ai enrich lead LEAD-2026-00031` | `@ai completa prospecto LEAD-2026-00031` |
| Create lead | `@ai new lead Juan Perez at Acme, juan@acme.mx` | `@ai nuevo prospecto Juan Perez en Acme` |
| Create opportunity | `@ai create opportunity 50L sanitizer for Acme` | `@ai crea oportunidad sanitizante 50L para Acme` |
| Help | `@ai crm` / `@ai crm help` | (same) |

### Sub-agents

| Agent | Trigger | Purpose |
|---|---|---|
| `lead_enricher` | `Lead.after_insert` | Fill company info, dedupe contact |
| `meeting_capturer` | `Communication.after_insert` (email) | Attach to right opp; create lead if unknown |
| `opportunity_mover` | `Opportunity.on_update` + hourly cron | Suggest stage advance, scan stalled opps |
| `follow_up_writer` | Intent dispatch | Draft follow-up emails (bilingual) |
| `pipeline_summarizer` | Daily cron | Build the morning brief |
| `deal_coach` | Intent dispatch | Recommend next-best action on any opportunity |

### Autonomy levels (Karpathy slider)

Set via `ai_agent_settings.crm_autonomy_level` (Int field, 0–4). Enforced by `raven_ai_agent.patterns.guardrails`. **Default = 1 (suggest only).**

| Level | Name | What's allowed |
|-------|------|----------------|
| 0 | observe | Read-only; no writes |
| 1 | suggest | Post proposals in Raven; human approves |
| 2 | enrich/draft | Safe writes (Lead enrichment, follow-up drafts) |
| 3 | stage_move | Advance opportunity stages, set amounts |
| 4 | autonomous | Send emails, full pipeline ownership |

Per-action overrides live in the optional `AI Action Policy` DocType (see patterns module install guide).

### Configuration

CRM-specific fields auto-added to **AI Agent Settings** by the v0.1.1 patch (`register_crm_agent`):

| Field | Type | Default | Purpose |
|---|---|---|---|
| `crm_autonomy_level` | Int | 1 | 0–4, see autonomy ladder above |
| `crm_digest_channel` | Link → Raven Channel | — | Where the daily digest posts |
| `crm_default_pipeline` | Data | "Sales" | Default opportunity pipeline |
| `crm_followup_language` | Select | "auto" | `en` / `es` / `auto` (auto-detects from contact) |
| `crm_section`, `crm_column_break` | UI | — | Layout in AI Agent Settings form |

### Tools exposed to LLM function-calling

All tools under `raven_ai_agent.skills.crm_agent.tools.*`, decorated with `@frappe.whitelist()` so they work from chat, ERPNext UI, and the LLM tool-call loop.

| Module | Functions |
|---|---|
| `leads` | `create_lead`, `update_lead`, `qualify_lead`, `convert_lead_to_opportunity`, `list_leads` |
| `opportunities` | `create_opportunity`, `move_stage`, `set_amount`, `list_open_opportunities`, `forecast` |
| `contacts` | `find_or_create_contact`, `enrich_contact`, `find_duplicates` |
| `customers` | `convert_lead_to_customer`, `link_contact` |
| `communications` | `log_communication`, `send_email` |
| `activities` | `create_todo`, `schedule_event`, `add_note` |
| `quotation` | `create_quotation_from_opportunity` (wraps `api/handlers/quotation.py`) |
| `search` | `semantic_search` (wraps `api/enhanced_search.py`) |

### Install / upgrade on a new site

```bash
# 1. Pull the cleanup branch
cd ~/frappe-bench/apps/raven_ai_agent
git fetch upstream
git checkout crm-V14.1.1   # or merged target branch once #17/#18 land

# 2. Run tests (must be 43/43)
cd ~/frappe-bench/apps/raven_ai_agent
python -m pytest raven_ai_agent/skills/crm_agent/tests/ -q

# 3. Migrate, scoped to a SINGLE site, as `frappe` (never root)
cd ~/frappe-bench
bench --site <your-site> backup
bench --site <your-site> migrate    # applies register_crm_agent patch

# 4. Verify (safe module-execute pattern, not console heredoc)
cat > apps/raven_ai_agent/raven_ai_agent/_verify.py <<'PY'
import frappe
def run():
    fields = frappe.get_all("Custom Field",
        filters={"dt":"AI Agent Settings","fieldname":["like","crm_%"]},
        fields=["fieldname"], order_by="fieldname")
    print("crm_* custom fields:", [f.fieldname for f in fields])
    assert len(fields) == 6, f"expected 6, got {len(fields)}"
    print("OK")
PY
bench --site <your-site> execute raven_ai_agent._verify.run
rm apps/raven_ai_agent/raven_ai_agent/_verify.py
```

### Rollback

```bash
# Pre-cleanup tag was created automatically:
git reset --hard pre-cleanup-v0.1.1-20260614_103913

# DB restore (replace path with your own pre-migrate backup):
bench --site <your-site> restore <path-to-pre-migrate-backup>.sql.gz
```

### Verification reference (v2.sysmayal.cloud, 2026-06-14)

| Check | Result |
|---|---|
| `pytest raven_ai_agent/skills/crm_agent/tests/` | 43/43 PASS in 0.031s |
| `bench migrate` exit code | 0 |
| Pre-migrate DB backup retained | 250.8 MiB |
| CRM custom fields created | 6 (see table above) |
| Skill identity | `name="crm-agent"`, `version="0.1.0"`, class `CRMAgentSkill` |
| `_default_currency()` resolved | `"MXN"` (fallback — no Company default on site) |
| Hooks wiring | All `doc_events` + `scheduler_events` targets resolve via `frappe.get_attr` |
| Idempotency (patch re-run) | 6 → 6 custom fields, no duplicates, no error |

## Known Issues & Resolutions

| Issue | Status | Resolution |
|-------|--------|------------|
| Mobile/Web channel visibility mismatch | ✅ Fixed | Sync Raven User table with ERPNext User |
| Sales Invoice creation failure | ✅ Fixed | Added mode_of_payment field to workflow |
| Command routing for !prefix | ✅ Fixed | Updated command_router.py |
| QMS Training Program field bug | ✅ Fixed | Field validation updates |
| CRM skill name inconsistency (snake vs kebab) | ✅ Fixed (v0.1.1) | Canonical kebab-case `crm-agent` everywhere |
| CRM patterns module missing (B1) | ✅ Fixed (v0.1.1) | Shipped `raven_ai_agent_patterns` v0.1.0 |
| CRM autonomy enforcement untested | ✅ Fixed (v0.1.1) | 43-test suite incl. autonomy + hook + audit |
| ES intent coverage gap on `deal_coach` (S4) | ✅ Fixed (v0.1.1) | Regex accepts EN form without preposition for ES parity |
| Bare `$` in CRM templates (M4) | ✅ Fixed (v0.1.1) | Currency-aware formatter |

---

## License

MIT
