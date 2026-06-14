---
name: crm_agent
description: Agentic CRM for ERPNext — humans supervise agents that enrich leads, advance opportunities, draft follow-ups, and summarize pipeline.
version: 0.1.0
author: Raven AI Agent
triggers:
  - lead
  - leads
  - opportunity
  - opportunities
  - pipeline
  - deal
  - deals
  - prospect
  - follow up
  - follow-up
  - followup
  - next step
  - next best action
  - enrich contact
  - enrich lead
  - move stage
  - close deal
  - customer
  - crm
  - prospecto
  - oportunidad
  - cliente
  - seguimiento
  - cotización
  - cotizar
patterns:
  - "(?:create|add|new)\\s+(?:a\\s+)?(?:lead|opportunity|contact|prospect|deal)"
  - "(?:show|list|view)\\s+(?:my\\s+)?(?:pipeline|leads|opportunities|deals)"
  - "(?:next|best)\\s+(?:step|action|move)\\s+(?:on|for)\\s+\\S+"
  - "(?:draft|write|compose)\\s+(?:a\\s+)?(?:follow[-\\s]?up|email|seguimiento)"
  - "(?:move|advance|set)\\s+(?:opp|opportunity|deal)\\s+\\S+\\s+to\\s+\\S+"
  - "(?:enrich|complete|completa)\\s+(?:lead|contact|prospect|prospecto)"
  - "(?:pipeline|deal)\\s+(?:summary|digest|status|report)"
  - "(?:qu[eé]\\s+sigue\\s+con|qu[eé]\\s+hacer\\s+con)\\s+\\S+"
metadata:
  raven:
    emoji: "🤝"
    category: crm
    priority: 65
    scope: agentic
    auto_invoke: true
  agents:
    - lead_enricher
    - meeting_capturer
    - opportunity_mover
    - follow_up_writer
    - pipeline_summarizer
    - deal_coach
  autonomy_levels:
    - level: 0
      name: observe
      description: Summarize only; never propose
    - level: 1
      name: suggest
      description: Propose actions in Raven channel; human approves
    - level: 2
      name: draft
      description: Draft emails/quotes; one-click send
    - level: 3
      name: act
      description: Execute safe writes (enrich, move stage, log)
    - level: 4
      name: autonomous
      description: Full autonomy on defined pipeline
  required_doctypes:
    - Lead
    - Opportunity
    - Contact
    - Customer
    - Communication
    - ToDo
    - Event
    - Quotation
  scheduler_events:
    daily:
      - raven_ai_agent.skills.crm_agent.agents.pipeline_summarizer.run_daily_digest
    hourly:
      - raven_ai_agent.skills.crm_agent.agents.opportunity_mover.scan_stalled_opportunities
---

# CRM Agent Skill

Agentic CRM for ERPNext, inspired by [item.app](https://item.app)'s
"humans supervise agents" model — but built on Frappe-native DocTypes
(`Lead`, `Opportunity`, `Contact`, `Customer`, `Communication`,
`Quotation`) and on the existing `raven_ai_agent` skill framework,
agent base, channels, and providers.

## Why it exists

Traditional CRMs require humans to *produce* data (log calls, update
stages, write follow-ups). This skill flips that: agents produce,
humans review. The same pattern item describes — but inside your
existing ERPNext stack, so it picks up Banxico FX, CFDI, quotation
flows, and your manufacturing/quality context for free.

## Capabilities (v1)

### Intents handled directly by the skill (`handle()`)

- Create a Lead from a one-liner
- List/filter pipeline
- Move opportunity stage
- Show next-best-action for any opportunity (delegates to `deal_coach`)
- Draft a follow-up (delegates to `follow_up_writer`)
- Daily pipeline digest (delegates to `pipeline_summarizer`)

### Triggered agents (via `doctype_events/`)

| Hook | Agent | Action |
|------|-------|--------|
| `Lead.after_insert` | `lead_enricher` | Fill company info, dedupe contact |
| `Communication.after_insert` (email) | `meeting_capturer` | Attach to right opp; create lead if unknown |
| `Opportunity.on_update` | `opportunity_mover` | Suggest stage advance |

### Scheduled (via `hooks.py`)

- `daily` — `pipeline_summarizer.run_daily_digest`
- `hourly` — `opportunity_mover.scan_stalled_opportunities`

## Tools exposed to LLM function-calling

All tools live under `raven_ai_agent.skills.crm_agent.tools.*` and are
plain Python functions decorated with `@frappe.whitelist()`, so they
work from chat, from the ERPNext UI, and from the LLM tool-call loop.

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

## Autonomy

Set `ai_agent_settings.crm_autonomy_level` (0–4). Enforced by
`raven_ai_agent.patterns.guardrails`. Default = 1 (suggest only).

## Usage Examples

```text
new lead Juan Perez at Acme, juan@acme.mx, interested in 5L sanitizer
show pipeline this week
what should I do next on Opp-0042?
draft follow-up for Opp-0042
move Opp-0042 to Quotation
morning brief
enrich lead LEAD-2026-00031
¿qué sigue con Opp-0042?
muéstrame el pipeline de esta semana
```

## Configuration

Add to `ai_agent_settings`:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `crm_autonomy_level` | Int | 1 | 0–4, see autonomy table |
| `crm_digest_channel` | Link → Raven Channel | — | Where the daily digest posts |
| `crm_default_pipeline` | Data | "Sales" | Default opportunity pipeline |
| `crm_followup_language` | Select | "auto" | en / es / auto (detect from contact) |

## See also

- Sibling plan: `CRM_SKILL_PLAN.md`
- Framework: `raven_ai_agent/skills/framework.py`
- Patterns: `raven_ai_agent/patterns/`
- Inspiration: item.app interview — [Startupeable](https://www.youtube.com/watch?v=bRkFMiuR5Es)
