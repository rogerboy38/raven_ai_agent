Paste this entire content into 00_ORCHESTRATOR_PROJECT_PLAN.md on GitHub.

Orchestrator Project Plan – Alexa → Raven → ERP
This document defines a 6‑phase plan to build and operate an AI‑orchestrated Alexa → Raven → ERPNext integration inside the raven_ai_agent Frappe app.

Phase 1 – Requirements and Use Cases
Scope
Stakeholders

Integrator / developer: designs and maintains the orchestrator and Frappe app (raven_ai_agent).
​

Internal business users (sales, finance, operations): speak to Alexa to trigger ERP actions or queries.
​

ERP administrators: configure Raven agents, permissions, and guardrails.
​

SRE / ops: monitor reliability, latency, and cost.

Interaction channels

Alexa Custom Skill (voice in, short confirmation voice out).
​

Raven channels (e.g. workspace “Voice”, channel #alexa-commands).
​

ERPNext / Frappe UI for approvals, configuration, and audit logs.
​

Core end‑to‑end workflows (v1)

Sales order drafting:

“As a sales user, I want to say ‘create a sales order for John for 10 units of item X’ so that a Draft Sales Order is created in ERPNext and logged in Raven.”
​

Reporting / queries:

“As a manager, I want to ask ‘what invoices are overdue?’ so that I get a quick summary in Raven without opening ERPNext.”
​

Expense logging:

“As an employee, I want to say ‘log an expense for 30 dollars taxi to client ACME’ so that a Draft Expense Claim is created.”

Status checks:

“As a user, I want to say ‘what is the status of sales order SO‑0001?’ so that I hear or see its status in Raven.”

Out‑of‑scope for v1 (examples)

Destructive operations: delete customers, cancel/submit documents, change BOMs, change critical configuration.

Direct PLC/industrial control via Alexa.

Multi‑step conversational confirmations over voice only (confirmation happens in Raven/ERP UI first).

Non‑functional requirements

Latency: P95 end‑to‑end (user speaks → Raven message posted) ≤ 8–10 seconds.

Availability: Alexa endpoint and Frappe API ≥ 99% during business hours.

Safety:

No destructive ERP change without explicit human approval or very explicit confirmation and allowed autonomy level.
​

Auditability:

Every Alexa request is logged with alexa_user_id, mapped frappe_user, text, intent, channel, and outcome.

Cost:

Keep average LLM cost per Alexa request below a defined ceiling, configurable per environment.

Test plan (Phase 1)
Reviews

Run a short requirements review with:

Dev/integrator, business user rep, ERP admin.

Artefact checks

Confirm this document lists:

Stakeholders, channels, in‑scope and out‑of‑scope operations, non‑functional requirements.

Consistency tests

For each workflow, link at least one business KPI (e.g. “time to create SO”, “number of ERP queries via voice per month”).

Verified goals (exit criteria)
This 00_ORCHESTRATOR_PROJECT_PLAN.md is approved and versioned in the repo.
​

Each workflow has:

Role, goal, business value, and high‑level constraints.

Risks and assumptions documented (e.g. LLM availability, Frappe Cloud limits, Alexa Skill review process).

Phase 2 – Orchestrator and Architecture Design
Target architecture
High‑level components

Alexa side:

Alexa Custom Skill with:

Invocation name (e.g. “Raymond”).

Intents that capture free‑form utterances (e.g. FreeFormIntent with one big slot).
​

Skill forwards text + metadata to an HTTPS endpoint (middleware).
​

Middleware / integration service (orchestrator entrypoint)

Could be an AWS Lambda or small FastAPI/Flask app.

Responsibilities:

Validate Alexa request signature and origin.
​

Extract speech‑to‑text result, intent name, slots, session id.
​

Map alexa_user_id → frappe_user and default Raven workspace/channel.
​

Call Frappe via HTTPS:

POST https://<site>/api/method/raven_ai_agent.api.alexa_to_raven with JSON body.
​

Return a simple Alexa response such as:

“Okay, I’ve sent that to your assistant in Raven.”
​

Frappe / Raven side (in raven_ai_agent)

Whitelisted method: raven_ai_agent.api.alexa_to_raven:

Validates API key/secret or bearer token from middleware.
​

Resolves mapping from Alexa user to Raven user/channel (DocType: Alexa User Mapping).

Uses a Raven Bot to post a message into the mapped channel, mentioning the AI agent:

@ai from Alexa (user X): <text>.
​

Optionally stores a log record in a DocType Alexa Request Log.

Raven workspace and channels:

Workspace “Voice”.

Channel #alexa-commands (plus optional per‑team channels).
​

Raven Bot:

Created in Raven settings and granted access to relevant channels; used by alexa_to_raven to send messages.
​

Raven AI Agent:

Configured in Raven and bound to #alexa-commands.

Uses your existing Raymond/Memento/Lucy/Karpathy protocols and tools for ERP/DocType operations.
​

Orchestration patterns
Sequential

Primary flow: Alexa → middleware → alexa_to_raven → Raven AI Agent → tools → response.
​

Concurrent

Within the AI agent, multiple tools may run concurrently (e.g. check credit + overdue invoices), but Alexa side stays sequential.

Handoff / group‑chat (optional later)

The same channel can have human + agent discussion; humans can override, approve, or correct actions.
​

Key APIs (sketch)
Middleware → Frappe

text
POST /api/method/raven_ai_agent.api.alexa_to_raven
Authorization: token <api_key:api_secret>
Content-Type: application/json

{
  "alexa_user": "amzn1.account.ABC123",
  "text": "create a sales order for John for 10 units of item X",
  "intent": "FreeFormIntent",
  "slots": {
    "utterance": "create a sales order for John for 10 units of item X"
  },
  "session_id": "alexa-session-uuid"
}
Frappe internal helper (conceptual)

python
def post_to_raven_channel(channel_name: str, message: str, as_bot: str) -> dict:
    """
    Posts `message` to Raven `channel_name` as bot `as_bot`,
    returns Raven message metadata.
    """
Failure handling
Middleware:

If Frappe returns 4xx (auth/mapping issue), Alexa says:

“I could not reach your assistant. Please contact your administrator.”

If Frappe returns 5xx, Alexa returns a generic error and logs an incident.

Frappe:

If mapping is missing, either:

Post into a default admin channel, or

Return a 400 with error “Unknown Alexa user mapping”.

Raven agent/tool failures:

The agent posts an error message in Raven, but the Alexa flow is still considered successful (it delivered the text).

Test plan (Phase 2)
Architecture review

Validate that diagrams cover:

Normal flow.

Frappe down, LLM down, or Raven error.

Interface checks

Confirm that the JSON payload above is documented and implemented for:

Middleware → Frappe.

Frappe internal helper → Raven.

Stress analysis (paper)

Consider multiple concurrent Alexa calls, Frappe rate limits, and timeouts.

Verified goals (exit criteria)
Architecture diagram and sequence diagrams checked in beside this plan (e.g. /docs/alexa_raven_architecture.drawio).

Decision log includes:

Orchestrator is embedded in raven_ai_agent (no separate microservice orchestrator for now).

Alexa flows are “fire‑and‑forget” to Raven; responses are not streamed back to Alexa v1.

Phase 3 – Agent and Tool Specification
Agents
Raven AI Agent (existing in raven_ai_agent)

Role: goal‑oriented ERP assistant that can interpret free‑form instructions and call Frappe tools.
​

Inputs:

Text messages in Raven channels where it listens (#alexa-commands, etc.) that mention @ai.
​

Outputs:

Text responses in Raven.

Tool calls that operate on DocTypes (Sales Order, Sales Invoice, Expense Claim, Reports, etc.).
​

Constraints:

For Alexa‑origin messages, restricted tool set and draft‑only actions.

(Optional later) Guardrail/router agent:

Implemented via prompt instructions, not a separate code component.

Tools (examples for v1)
These are conceptual and should map to Frappe whitelisted methods.

create_sales_order

Description: Create a Draft Sales Order for a customer with simple item list.

Input:

customer (string, required).

items (list of { item_code: string, qty: float }).

source (string, default "alexa").

Output:

{ "name": "SO-0001", "status": "Draft" }

Side‑effects:

Inserts a Sales Order in ERPNext with source = "alexa" or a custom field flag.

Permissions:

Only if mapped frappe_user has Sales Order creation rights and “Alexa Voice” role.

list_overdue_invoices

Description: Return a summary of overdue Sales Invoices for a given company or customer.

Input:

company (string, optional).

customer (string, optional).

Output:

List of { "invoice": str, "customer": str, "amount": float, "due_date": date }.

Side‑effects:

None (read‑only).

create_expense_claim

Description: Create a Draft Expense Claim on behalf of a user, for simple single‑line expenses.

Input:

employee or user.

amount.

description.

Output:

{ "name": "EXP-0001", "status": "Draft" }

Side‑effects:

Draft Expense Claim created, flagged as Alexa‑origin.

(You can extend this catalog over time.)

Guardrails
In Raven agent system prompt:

“For messages tagged as Alexa‑origin, only use tools that are read‑only or create Drafts. Never submit/cancel/delete documents. If a destructive action is requested, explain that it requires manual approval in ERPNext.”

Tool‑level:

Frappe whitelisted methods check:

frappe_user’s roles.

A flag allow_voice_operation on DocType or on user.

Routing rules (conceptual)
All Alexa‑origin text goes to the same Raven AI Agent but with additional context:

e.g. source = "alexa" and alexa_user_id in metadata.
​

The agent decides which tool to use based on intent:

“create”, “new” → creation tools.

“what”, “list”, “show” → reporting tools.

Test plan (Phase 3)
Spec validation

For each tool, document:

Input/output schema, side‑effects, permission checks.

Intent walkthroughs

Take at least 20 sample voice commands and:

Manually decide which tool they should trigger.

Verify the agent prompt/instructions will route correctly.

Safety review

Try to derive potential unsafe behaviour (e.g. mis‑parsing numbers or customers) and adjust constraints.

Verified goals (exit criteria)
Agent/tool catalog documented (Markdown or JSON/YAML) in the repo.

At least 90% of the initial intents map to a clear tool or read‑only answer path in review sessions.

Destructive operations are forbidden at the tool layer for Alexa‑origin tasks.

Phase 4 – Implementation Plan and Integration
Implementation epics
Frappe integration (in raven_ai_agent)

Add alexa_to_raven whitelisted method:

File: raven_ai_agent/api/alexa.py (or similar).

Logic:

Parse JSON payload.

Validate token.

Resolve alexa_user mapping (DocType).

Build message string tagging @ai.

Use existing Raven channel utility functions to post as bot.
​

Create DocTypes:

Alexa User Mapping:

Fields: alexa_user_id, frappe_user, default_workspace, default_channel.

Alexa Request Log:

Fields: alexa_user_id, frappe_user, text, intent, channel, status, timestamps.

Configure Raven workspace, channel, and bot as described.
​

Middleware / Alexa backend

Choose stack (AWS Lambda node/python, FastAPI, etc.).

Implement:

Alexa request validation.

Extraction of free‑form text.

POST to Frappe API as per Phase 2.
​

Implement basic error handling and logging.

Alexa Skill configuration

Define interaction model:

Invocation name.

At least one free‑form intent capturing arbitrary text.
​

Configure endpoint to middleware.

Test with sample utterances using Alexa developer console.

Raven AI Agent configuration

Update the agent’s system prompt to include:

Alexa‑origin context.

Guardrails and allowed tools.
​

Ensure tools (whitelisted methods) are exposed in a way the agent can call (existing integration backends).

CI/CD and configuration

Add tests for alexa_to_raven in your Frappe app tests.

Add config for:

Frappe site URL, API keys, and environment flags in middleware.

Use environment variables for secrets (no hard‑coded keys).

Test plan (Phase 4)
Unit tests

For alexa_to_raven:

Valid payload → Raven post called with correct channel/message.

Invalid token → 401/403.

Missing mapping → 400 or fallback behaviour.

Integration tests

Local or staging:

Simulate Alexa request in middleware test harness, verify:

Frappe receives call.

Raven channel gets message.

AI Agent replies.

Verified goals (exit criteria)
All core flows pass in staging:

A scripted POST from middleware to alexa_to_raven results in a Raven conversation and (if applicable) draft document creation.

No open critical defects in integration tests.

Phase 5 – Testing, Evaluation, and Safety
Test strategy
Unit tests

Frappe methods used as tools (e.g. create Sales Order) have tests for:

Valid inputs.

Validation failures.

Permission failures.

End‑to‑end tests

Golden‑path scenarios:

create_sales_order from Alexa.

list_overdue_invoices from Alexa.

create_expense_claim from Alexa.

Edge cases:

Ambiguous customer names.

Unknown item codes.

Missing quantities or inconsistent units.

Adversarial tests

Attempt to get the agent to:

Delete data.

Submit or cancel documents.

Exfiltrate secrets or API keys.

Ensure guardrails and permissions prevent action.

Metrics
Task success rate:

Percentage of Alexa requests that result in a sensible agent answer and, if applicable, a valid draft ERP document.

Latency:

Time from Alexa invocation to message appearing in Raven.

Cost:

Average LLM cost per request (tracked via provider dashboard; optionally logged).

Safety incidents:

Count of blocked unsafe attempts (logged from guardrails).

Guardrails
Input filtering:

Optional: basic profanity filter at middleware level.

Permission checks:

Frappe methods verify user roles, allow_voice_operation, and environment (dev/stage/prod).

Approval flow:

For operations beyond draft creation, require explicit approval click in ERPNext or explicit Raven confirmation and a high autonomy level.
​

Test plan (Phase 5)
Build a small library of test utterances (JSON file) and a script to replay them against staging.

Review outputs for correctness and safety.

Verified goals (exit criteria)
Target success rate reached for golden‑path scenarios (e.g. ≥ 95%) and acceptable for noisy inputs (≥ 90%).

No known prompt‑injection scenario can bypass guardrails for destructive operations.

Latency and cost within predefined envelopes.

Phase 6 – Deployment, Operations, and Continuous Improvement
Deployment
Environments

Dev: local and dev Frappe Cloud site; dev Alexa Skill.

Stage: stage site with sanitized data and staging Skill.

Prod: live ERPNext and Raven site plus production Skill.

Rollout strategy

Shadow mode:

Enable Skill for a small set of users; results go to non‑critical channels or are not used for real actions initially.

Gradual expansion:

Add more users and more tools once stability and safety are proven.

Rollback:

Disable Alexa Skill or switch middleware to a stub that returns “service under maintenance” if needed.

Monitoring and alerting
Frappe

Monitor:

Errors from alexa_to_raven.

Volume of Alexa requests (via Alexa Request Log).

Middleware

Monitor:

4xx/5xx error rates.

Latency to Frappe.

Number of Alexa requests per user.

LLM / Raven

Monitor:

Agent errors.

Cost per day for Alexa‑origin sessions.

Alerts

Alert when:

Error rate exceeds threshold.

Latency spikes beyond SLA.

Safety incident count rises unusually.

Feedback and continuous improvement
Capture:

Raven reactions (thumbs/emojis) on agent responses.

User comments and manually tagged “bad” responses.

Process:

Monthly review meeting:

Examine metrics, incidents, and common failure utterances.

Adjust prompts, tools, mappings, and guardrails.

Plan new capabilities (additional tools, new workflows).

Governance
Introduce new tools/agents:

Require:

Spec update.

At least basic tests.

Review by ERP admin and integrator.

Deprecation:

Announce, remove from prompts, then decommission tool endpoints.

Verified goals (exit criteria)
Production deployment live with:

Documented rollback.

Dashboards for health and usage.

On‑call or at least a named person responsible for incidents.

Continuous improvement cadence established (e.g. monthly review with issues created in GitHub from findings).
