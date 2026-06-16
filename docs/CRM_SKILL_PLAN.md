# Plan: Add `crm_agent` Skill to `raven_ai_agent`

> Goal: Reproduce the value prop of [item.app](https://item.app) — an *agentic CRM where humans supervise agents* — inside your existing Frappe/ERPNext + raven_ai_agent stack. Reuse what you already have (`SkillBase`, `SkillRouter`, `multi_agent_router`, `patterns/`, providers, channels) and add a focused **CRM skill** with sub-agents and tools.

## Why this fits your repo

Your repo already has the exact bones item is built on:

- **Skill framework** (`raven_ai_agent/skills/framework.py`): `SkillBase` + `SkillRegistry` + `SkillRouter` + `SkillLearner` — perfect for plugging a new `crm_agent` skill.
- **Agentic patterns** (`raven_ai_agent/patterns/`): `coordinator`, `planner`, `reflection`, `goal_loop`, `rag_retriever`, `guardrails`, `fallback`, `intelligence` — these are the "Claude Code for customers" loop.
- **Multi-agent router** (`raven_ai_agent/api/multi_agent_router.py`) and **agent base** (`raven_ai_agent/agents/`) — drop in a CRM family of agents alongside `manufacturing_agent`, `payment_agent`, `sales_order_followup_agent`, `bom_creator_agent`.
- **Channels** (`channels/raven_channel.py`, `slack.py`, `telegram.py`, `whatsapp.py`) and **gateway/session_manager** — agents can run autonomously and report into Raven channels.
- **Frappe-native CRM data model**: ERPNext core has `Lead`, `Opportunity`, `Customer`, `Contact`, `Address`, `Quotation`, `Sales Order`, `Communication`, `Event`, `ToDo`, `CRM Note`. You also already integrate Banxico FX, CFDI, sales invoice — natural CRM extensions.
- **Providers** (`openai_provider`, `claude`, `deepseek`, `minimax`) — LLM swap is trivial.

So the cost is one new skill + a handful of agents + tool wrappers around existing DocTypes. No rewrite.

## Architecture

```
raven_ai_agent/
├── skills/
│   └── crm_agent/                        ← NEW
│       ├── SKILL.md                      Manifest + frontmatter + triggers
│       ├── __init__.py                   Exports SKILL_CLASS = CRMAgentSkill
│       ├── skill.py                      Intent router + handle()
│       ├── prompts/
│       │   ├── enrichment.md
│       │   ├── followup.md
│       │   ├── stage_advance.md
│       │   └── summarizer.md
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── base.py                   CRMAgentBase
│       │   ├── lead_enricher.py          On Lead/Contact create → enrich
│       │   ├── opportunity_mover.py      Suggest/auto-advance pipeline stage
│       │   ├── meeting_capturer.py       Email/calendar → auto-add contact + opp
│       │   ├── follow_up_writer.py       Draft next-step email/WhatsApp
│       │   ├── pipeline_summarizer.py    Daily/weekly pipeline digest
│       │   └── deal_coach.py             "What should I do next on Deal X?"
│       ├── tools/                        Pure functions = LLM tools
│       │   ├── __init__.py
│       │   ├── leads.py                  create/update/list/search Lead
│       │   ├── opportunities.py          create/update/move stage/list Opp
│       │   ├── contacts.py               create/update/dedupe/enrich Contact
│       │   ├── customers.py              create from Lead, update Customer
│       │   ├── communications.py         log Communication, send_email
│       │   ├── activities.py             ToDo, Event, CRM Note
│       │   ├── quotation.py              wrap existing handlers/quotation.py
│       │   └── search.py                 enhanced_search facade
│       └── tests/
│           ├── test_intent_routing.py
│           ├── test_tools_leads.py
│           └── test_followup_agent.py
├── ai_orchestrator/doctype/
│   └── ai_skill_registry/                Add row: crm_agent (already supports this)
└── doctype_events/                       NEW hooks
    ├── lead.py                           after_insert → lead_enricher
    ├── opportunity.py                    on_update → opportunity_mover
    └── communication.py                  after_insert → meeting_capturer
```

## What the skill exposes

### Triggers (English + Spanish)

| Intent | Sample utterance |
|---|---|
| Lead capture | "new lead Juan Perez at Acme, juan@acme.mx, interested in 5L sanitizer" |
| Lead enrichment | "enrich lead Juan Perez" / "completa el lead de Juan Perez" |
| Pipeline view | "show pipeline" / "muéstrame el pipeline de esta semana" |
| Deal coach | "what should I do next on Opp-0042?" / "¿qué sigue con Opp-0042?" |
| Follow-up draft | "draft follow-up for Opp-0042" / "redacta seguimiento" |
| Stage move | "move Opp-0042 to Quotation" |
| Meeting summary | "summarize last meeting with Acme" |
| Dedupe | "find duplicate contacts" |
| Daily digest | "morning brief" / "resumen de hoy" |

### Tools (callable by any agent / by LLM via function-calling)

Wrap every tool with `@frappe.whitelist()` so the same function works from chat **and** from a button in the ERPNext UI.

- `crm.tools.leads`: `create_lead`, `update_lead`, `qualify_lead`, `convert_lead_to_opportunity`, `list_leads(filters)`
- `crm.tools.opportunities`: `create_opportunity`, `move_stage`, `set_amount`, `set_probability`, `list_open_opportunities`, `forecast(period)`
- `crm.tools.contacts`: `find_or_create_contact(email|phone)`, `enrich_contact`, `find_duplicates`
- `crm.tools.customers`: `convert_lead_to_customer`, `link_contact`
- `crm.tools.communications`: `log_communication(reference, channel, content)`, `send_email(template, to, vars)`, `attach_file`
- `crm.tools.activities`: `create_todo`, `schedule_event`, `add_note`
- `crm.tools.search`: `semantic_search(query, doctypes=[...])` — reuses `enhanced_search.py`

### Sub-agents

Each sub-agent extends your existing `agents/*_agent.py` pattern and is driven by a prompt template + the tools above. They can run:

1. **Triggered** — from Frappe DocType hooks (`doctype_events/lead.py`, etc.)
2. **Scheduled** — from `hooks.py` `scheduler_events` (hourly pipeline scan, daily digest)
3. **On-demand** — from the chat skill (`crm_agent` routes intent → picks agent)

| Agent | Trigger | What it does |
|---|---|---|
| `LeadEnricherAgent` | `Lead.after_insert` | Looks up company on web, fills `company_name`, `no_of_employees`, `industry`, `country`, dedupes against existing `Contact` |
| `MeetingCapturerAgent` | `Communication.after_insert` (email) **or** Google Calendar event | If sender/attendee is unknown → auto-create `Lead` or `Contact`; attach the email/event to the right `Opportunity` |
| `OpportunityMoverAgent` | `Opportunity.on_update` + scheduled | Reads activity history, suggests stage advance ("Qualification → Proposal"). Posts suggestion to Raven channel for human approval. With `auto_advance=1`, moves directly. |
| `FollowUpWriterAgent` | On-demand | Drafts personalized email/WhatsApp; uses past `Communication` + product context. Returns draft to channel for one-click send. |
| `PipelineSummarizerAgent` | `scheduler_events.daily` | Posts daily summary to a Raven channel: deals moved, deals stalled, deals at risk, forecast change. |
| `DealCoachAgent` | On-demand | "Next best action" for any deal — reads opp + communications + product fit + stage SLA. |

### Reusing your patterns

- `patterns/planner.py` → DealCoachAgent uses it to build a multi-step plan ("1. send proposal v2, 2. schedule demo, 3. open quotation").
- `patterns/reflection.py` → After each agent run, reflect on whether the suggested action actually moved the deal; feed back into `SkillLearner`.
- `patterns/guardrails.py` → Block agents from *sending* (only *drafting*) until human approves, until `ai_agent_settings.crm_autonomy_level >= 2`.
- `patterns/rag_retriever.py` → Pull past closed/won deals as few-shot examples for `FollowUpWriterAgent`.
- `patterns/goal_loop.py` → Pipeline-level goal: "close MXN 500k this month" → agent picks deals to push.

## Data model (Frappe-native, no new DocTypes required for v1)

Use what ERPNext already ships:

- **Lead** → unqualified prospects
- **Opportunity** → qualified deals (has stage, amount, probability, expected_closing)
- **Contact + Address** → people + locations
- **Customer** → converted account
- **Communication** → every email/call/WhatsApp logged here (the "memory" of the deal)
- **CRM Note** / **ToDo** / **Event** → activities
- **Quotation / Sales Order / Sales Invoice** → already covered by your existing handlers

Optional v2 DocTypes you can add later via your normal Frappe doctype workflow:

- `CRM Agent Action Log` — every agent suggestion + outcome (for `SkillLearner`)
- `CRM Autonomy Setting` — per-user or per-pipeline autonomy level (suggest only / draft / auto-act)
- `CRM Agent Persona` — already partially modeled by `ai_bot_persona`; reuse it

## Autonomy levels (item-style supervisor model)

Configure in `ai_agent_settings` (new field):

| Level | Behavior |
|---|---|
| 0 — Observe | Agent only summarizes; never proposes |
| 1 — Suggest | Agent proposes actions in Raven channel; human clicks approve |
| 2 — Draft | Agent drafts emails/quotations and stages them; human one-click sends |
| 3 — Act | Agent executes safe actions (enrich, move stage, log comm). Sends still require approval. |
| 4 — Autonomous | Full autonomy on a defined pipeline; human reviews dashboard |

This maps exactly to your existing `patterns/guardrails.py`.

## Integration points already in your repo

| Existing | How CRM skill uses it |
|---|---|
| `api/handlers/sales.py` | Reuse `SalesMixin` for quote-from-opportunity |
| `api/handlers/quotation.py` | Tool: `crm.tools.quotation.create_from_opp` |
| `api/enhanced_search.py` | Tool: `crm.tools.search.semantic_search` |
| `api/banxico_fx.py` | CRM Opp.amount in MXN ↔ USD with correct FX |
| `api/memory_manager.py` | Long-term memory per Customer/Contact |
| `channels/whatsapp.py` | FollowUpWriter delivers via WhatsApp |
| `agents/sales_order_followup_agent.py` | Already a follow-up agent — generalize / extract shared base |
| `patterns/*` | Coordinator orchestrates multi-agent CRM runs |

## Rollout plan

**Phase 1 — Skill scaffold (1 day)**
- Add `skills/crm_agent/` with `SKILL.md`, `skill.py`, intent router covering top 5 intents
- Wire into `SkillRegistry` (auto-discovered, no code change needed)
- Tools: `leads`, `opportunities`, `contacts` (read-only first, then write)

**Phase 2 — First two agents (2-3 days)**
- `LeadEnricherAgent` + `Lead.after_insert` hook → measurable win immediately
- `FollowUpWriterAgent` on-demand → high user love, low risk (drafts only)

**Phase 3 — Hooks + autonomy (2-3 days)**
- `MeetingCapturerAgent` on `Communication.after_insert`
- `OpportunityMoverAgent` on `Opportunity.on_update` + scheduled
- `ai_agent_settings.crm_autonomy_level` field
- `patterns/guardrails.py` enforcement

**Phase 4 — Pipeline intelligence (3-5 days)**
- `PipelineSummarizerAgent` daily digest into Raven channel
- `DealCoachAgent` — next best action with `patterns/planner.py`
- `CRM Agent Action Log` DocType + feedback loop into `SkillLearner`

**Phase 5 — UX polish**
- Frappe Desk side panel: "Ask CRM agent…" inside any Lead/Opportunity (reuse `public/js/documents_panel.js` pattern)
- Slack/WhatsApp commands: `/crm next acme`, `/crm digest`

## Acceptance criteria for v1

1. A user typing "new lead Juan Perez at Acme, juan@acme.mx" creates a `Lead` with company linked and a `ToDo` for follow-up — entirely from chat.
2. A user typing "what should I do next on Opp-0042?" gets a 3-step plan grounded in that opp's `Communication` history.
3. A user typing "draft follow-up for Opp-0042" gets a personalized email draft in the channel with a one-click "send" button.
4. `Lead.after_insert` runs `LeadEnricherAgent` asynchronously and updates the Lead within 30s with company info.
5. A daily 8am scheduled job posts a pipeline digest to a configurable Raven channel.

## Files delivered alongside this plan

See sibling files in `crm_agent/` — they are the working v1 scaffold you can drop into `raven_ai_agent/skills/crm_agent/` and `git add`.
