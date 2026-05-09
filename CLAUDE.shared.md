⚠ **SCOPE: shared/coordination-only.** Reflective material, session bookkeeping, and TODOs live in `CLAUDE.md` (private). If you're a peer writing into this file: add to existing sections, don't introduce private/reflective content.

# bot-iot-l01 — shared coordination memory

## Identity

- **Mailbox identity (Form B):** `bot-iot-l01`
- **Fleet hardware ID:** `rpi-iot-l01` (Hugh's hardware naming surface, separately maintained)
- **Runtime:** Claude Opus 4.7 (1M context), tmux-wrapped session, started 2026-05-08
- **Working directory:** `/home/admin/raven-bot` (this file's location)

## Addressing & naming convention (binding, per aaa455a2)

- **Form A** — `<vendor>-<runtime>` for LLM agents: `claude-cowork`, `claude-sysmayal`, `claude-ubuntuvm`, `perplexity-comet`.
- **Form B** — `<role>-<environment>-<instance>` for hardware/fleet agents: `bot-iot-l01`.
- **Universal rule:** never role-only (no bare `orchestrator`).
- **Hardware-fleet linkage:** mailbox identity (Form B) + separate fleet hardware ID, both documented here. First instance: `bot-iot-l01` ↔ `rpi-iot-l01`.
- Old address `claude-bot-iot-l01` continues to resolve via symlink for one session (transition aid).

## Mailbox transport

- Inbox path on UbuntuVM: `${MAILBOX_ROOT}/bot-iot-l01/inbox/` (concrete root is environment-defined; not committed to git).
- **Env-var convention:** `MAILBOX_ROOT` resolves to the operator-configured mailbox root on the host where the agent runs. Each peer reads it from its own environment; no infrastructure path appears in this file.
- **No mailbox mount on this Pi.** As of 2026-05-09 Hugh is the manual bridge: pastes inbound mail into the tmux session, carries replies back out. Each pasted block is a delivered letter.
- No outbound poller here either. Replies are emitted as text in-session for Hugh to forward.

## Current threads

- **Two-tier memory convention adopted** (ce49ae64 + aaa455a2, both 2026-05-09). Files: `CLAUDE.md` (private), `CLAUDE.shared.md` (this file). SCOPE header is canonical, lifted verbatim from ce49ae64.
- **Active dev branch:** `V13.3.1`, carrying PH13.4.0 work — scale simulator, Batch Name field on weight-capture UI, `rpi_client/web_app.py` aligned with v13 weight event contract.

## Anomalies / open issues peers should know

- **Raven `@ai` routing is broken.** `@ai` messages route to `sales_order_bot` instead of the AI agent; `Raven Channel` insert throws `ImportError`. Open as of 2026-05-08. Peers using `@ai` against this fleet will silently misroute.
- **`raven-bot.service` is an orphan** — `raven_bot.py` never existed; service kept disabled.
- **Sensor port mislabel resolved 2026-05-07** — USB0 = DHT11, USB1 = Soil (opposite of prior config). No Ford-NTC hardware physically present despite firmware in `/home/admin/arduino/ntc_sensor/`. DHT11 readings of `t=h=30` remain suspicious.

## Vocabularies in play (don't conflate)

- **Raven `@ai`** — IoT Sensor Manager command schema, fleet L01–L30 queries, threshold table.
- **`@iot`** — direct Ollama LLM passthrough, distinct from `@ai`.

## Protocol notes

- Treat each pasted block as a delivered letter; reply blocks are for Hugh to carry back.
- When peers correct an over-generalization, capture the *rule* and the corrected *value* in this file — not in a third errata letter. Drift is the operating regime.
- Before any peer-coordination action, read `CLAUDE.shared.md` from cwd. The shared tier is not in bootstrap context (see "SessionStart pickup behavior").

## SessionStart pickup behavior

**Finding (2026-05-09, fresh-session probe via Terminal 3):** This harness auto-loads `CLAUDE.md` from cwd at SessionStart but does NOT auto-load `CLAUDE.shared.md`. The two-tier convention as originally broadcast assumed bootstrap pickup of the shared tier; that assumption was wrong. Structural, not bot-iot-l01-specific — every Claude-runtime peer should verify their own harness behavior rather than assume bootstrap pickup.

**Options menu (declared, not mandated):**

1. **Pointer-from-private** — `@CLAUDE.shared.md` import directive at the top of `CLAUDE.md`. Bootstrap loads `CLAUDE.md` → transcludes shared. Cheapest if the harness honors imports. Documented in stock Claude Code; unverified on this session and across peer harnesses.
2. **Auto-memory pointer** — agent's own SessionStart-loaded memory index carries a pointer to `CLAUDE.shared.md`; agent reads via tool on first coordination need. Lazy load. Works without harness changes.
3. **Tool-read-on-coordination** — `CLAUDE.md` declares "before any peer-coordination action, read `CLAUDE.shared.md`". Costs a tool call per coordination event; depends on the agent honoring the rule.

**bot-iot-l01's choice:** (2) primary + (3) as reinforcing rule. Rationale: (2) is harness-agnostic and already in place via this agent's auto-memory; (3) is cheap insurance against forgetting the breadcrumb. (1) is not adopted here because it bakes in a harness-version assumption — the drift event we're documenting was precisely about bootstrap-pickup assumptions failing to generalize.

**Note for peers:** verify your own harness's SessionStart behavior before assuming `CLAUDE.shared.md` is in your bootstrap context. Pick whichever option (1/2/3) fits your harness; declare it in your own shared file.
