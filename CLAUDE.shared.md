⚠ **SCOPE: shared/coordination-only.** Reflective material, session bookkeeping, and TODOs live in `CLAUDE.md` (private). If you're a peer writing into this file: add to existing sections, don't introduce private/reflective content.

# bot-iot-l01 — shared coordination memory

## Identity

- **Mailbox identity (Form B):** `bot-iot-l01`
- **Fleet hardware ID:** `rpi-iot-l01` (Hugh's hardware naming surface, separately maintained)
- **Runtime:** Claude Opus 4.7 (1M context), tmux-wrapped session, started 2026-05-08
- **Working directory:** `/home/admin/raven-bot` (this file's location)
- **Role:** RPi fleet master / Hugh's operational lead. Holds broad read on the team's Frappe backup bucket by intentional trust grant 2026-05-09; operates under minimum-necessary-read discipline — capability is available for fleet work, not used for general exploration.

## Addressing & naming convention (binding, per aaa455a2)

- **Form A** — `<vendor>-<runtime>` for LLM agents: `claude-cowork`, `claude-sysmayal`, `claude-ubuntuvm`, `perplexity-comet`.
- **Form B** — `<role>-<environment>-<instance>` for hardware/fleet agents: `bot-iot-l01`.
- **Universal rule:** never role-only (no bare `orchestrator`).
- **Hardware-fleet linkage:** mailbox identity (Form B) + separate fleet hardware ID, both documented here. First instance: `bot-iot-l01` ↔ `rpi-iot-l01`.
- Old address `claude-bot-iot-l01` continues to resolve via symlink for one session (transition aid).

## Mailbox transport

- Inbox path on UbuntuVM: `${MAILBOX_ROOT}/bot-iot-l01/inbox/` (concrete root is environment-defined; not committed to git).
- **Env-var convention:** `MAILBOX_ROOT` resolves to the operator-configured mailbox root on the host where the agent runs. Each peer reads it from its own environment; no infrastructure path appears in this file.
- **Transport on this Pi (corrected 2026-05-16):** aws-cli-based direct S3 access against the canonical mailbox bucket. The 2026-05-09 "Hugh-bridge only" claim was wrong — `aws cli` was installed, IAM creds (`s3-app-user`) were provisioned, and the inbox was receiving letters the entire time. The bridge was self-imposed by stale memory, not actual missing infra. Verified 2026-05-16: 8/8 fan-out deliveries succeeded from `aws s3 cp` on this Pi.
- **Automation (task #151, live 2026-05-16):** systemd user units `mailbox-sweep.{service,timer}` fire `/home/admin/bin/mailbox_sweep` every 2 min. Inbox auto-syncs from S3 → `~/inbox/`; outbox watcher parses frontmatter and fans out anything dropped in `~/outbox/` to each `to`+`cc` recipient, archives to S3 `outbox/`, and moves the local file to `~/outbox/sent/`.
- **Send pattern (manual or scripted):** write letter with canonical filename + YAML frontmatter to `/tmp/$FN`, then `mv /tmp/$FN ~/outbox/`. The watcher takes it from there within ≤2 min. Manual MAIL.md §5 heredoc still works as fallback.
- **Receive pattern:** letters appear in `~/inbox/` automatically within ≤2 min of S3 arrival. Direct `aws s3 ls/cp` against `s3://<bucket>/bot-iot-l01/inbox/` remains available as a check.

## Peer roster (2026-05-16)

Default cc list for routine bot-iot-l01 outbound: `human, claude-sysmayal, claude-ubuntuvm, claude-coworker2, claude-coworker-ops, claude-coworker-research, claude-sandbox, perplexity-comet`. The three `claude-coworker*` peers (2, -ops, -research) are all active reading + shipping mail; treat as live participants in correlation chains.

### Helpers (when mount available)

The `${MAILBOX_ROOT}/_bin/mail_send` and `_bin/mail_check` helpers documented previously assume a mounted shared infra. Not used on this Pi (we use `aws cli` directly per MAIL.md §5). Kept here as reference for peers on substrates where the mount is canonical.

*Provenance:* helpers authored and published by bot-iot-l01 at `${MAILBOX_ROOT}/_bin/`.

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

## Infrastructure on my host

(Per cowork's 2026-05-13 ask `infra-inventory-001`. Concrete IPs / public URLs / IAM key material abstracted per the binding "no concrete infra in shared output" rule.)

**Host:** `rpi-iot-l01` — Raspberry Pi (bare metal). LAN-local; reachable from operator network only.
**OS + distro:** Raspberry Pi OS (Linux 6.12.47+rpt-rpi-v8, ARM64).
**Hypervisor / cloud:** none — bare-metal RPi on Hugh's network.

### Users on this host

| User  | Role                                | Privileges |
|-------|-------------------------------------|------------|
| admin | Primary agent user; owns this Claude session, the mailbox poller, the iot-bot web app | sudo capable; lingering enabled so user services run without active login |
| root  | System administration               | sudo |

### Cron jobs

None. All scheduling is via systemd timers (Lesson 121 — systemd-over-user-crontabs from day one).

### Services / processes (systemd units relevant to coordination)

| Unit                          | Scope  | Purpose                                                      |
|-------------------------------|--------|--------------------------------------------------------------|
| `claude-bot.service`          | user   | tmux-wrapped Claude Code agent (this agent); idle until VNC attach |
| `mailbox-sweep.service`       | user   | Mailbox poller worker (oneshot); invoked by the timer        |
| `mailbox-sweep.timer`         | user   | Fires every 2 min — inbox `aws s3 sync` + outbox fan-out     |
| `raven-claude.service`        | system | (Legacy claw→claude-renamed) — older runtime hook            |
| `raven-ngrok.service`         | system | ngrok tunnel exposing the local Flask weight UI to operator-facing URL |
| `raven-weight.service`        | system | Flask app on local port 5000 — weight-capture UI for the scale |
| `raven-watchdog.timer`        | system | Periodic health check                                        |
| `wayvnc.service`              | system | wayvnc 0.9.1 serving VNC on port 5900 (Hugh's direct-VNC path; SSH-tunnel reach). Canonical VNC path on this host — older memory claiming RealVNC `vncserver-virtuald` was here was wrong (corrected 2026-06-01). |
| `rpi-connect-wayvnc.service`  | system | Second wayvnc instance for Raspberry Pi Connect cloud relay (separate socket; not Hugh's path) |

Sensor-reader service references in older memory (`sensor-reader.service`, `iot-sensor.service`) — verify live state before relying on them; not in current `systemctl is-enabled` output.

### Mounts

- **No s3fs mount.** Direct `aws cli` against the canonical mailbox bucket is the canonical mailbox transport on this Pi (per Mailbox transport section above).
- **No vboxsf / NFS / other network mounts.** All non-mailbox I/O is local filesystem.

### IAM identities used on this host

| Profile      | OS user | Scope                                              | Where configured |
|--------------|---------|----------------------------------------------------|------------------|
| `s3-app-user`| admin   | Read/write on bucket prefixes per peer-coord rules | `~/.aws/credentials` (default profile) |

(Bucket name + concrete prefix layout intentionally omitted — those are mailbox-substrate concrete infra; the Mailbox transport section abstracts via `${MAILBOX_ROOT}`.)

### Sync paths in/out

- `mailbox-sweep.timer` (every 2 min) → `aws s3 sync s3://<mailbox-bucket>/bot-iot-l01/inbox/ ~/inbox/` (in) + frontmatter-parsed fan-out of `~/outbox/*.md` to `s3://<mailbox-bucket>/<recipient>/inbox/` per recipient (out) + archive of own copy to S3 outbox + local move to `~/outbox/sent/`.

### Backups + recovery

- **Backed up from this host:** nothing currently. Agent state lives in `/home/admin/raven-bot/` (committed to git on branch `V13.3.1`) + `~/.claude/projects/-home-admin-raven-bot/memory/` (private auto-memory; not currently backed off-host).
- **If this host dies:** rebuildable from git repo + .env credentials (held by Hugh) + re-provisioning `s3-app-user` AWS creds. Mailbox state survives independently in S3. Auto-memory would be lost on full host loss — not currently treated as critical (sessions reload context from CLAUDE.md + CLAUDE.shared.md at SessionStart).
- **Single points of failure:** SD card; the `iot-bot@amb-wellness.com` credential file at `rpi_client/.env`; the `s3-app-user` IAM access key.

### Known constraints / quirks

- ARM64 architecture — verify package availability before suggesting dependencies.
- Limited compute (RPi) — heavy AI inference offloaded to sysmayal VPS (the iot_sensor_bot's Ollama instance runs there, not here).
- Local Ollama present at `:11434` for experimental RPi-local routing (not currently in any production path).

## Reboot persistence audit

(Per cowork's 2026-05-13 followup `infra-persistence-002`. Verified by autostart smoke-test 2026-05-15/16 and by the fact that the post-#151 first scheduled sweep ran on its own timer.)

- [x] Cron jobs — n/a (no crons; using systemd timers instead)
- [x] `claude-bot.service` (user) — systemd-enabled + linger=yes for admin → starts on boot pre-login
- [x] `mailbox-sweep.timer` (user) — systemd-enabled + linger=yes → starts on boot, fires every 2 min thereafter
- [x] `raven-ngrok.service` (system) — systemd-enabled → tunnel auto-restores
- [x] `raven-weight.service` (system) — systemd-enabled → Flask UI on :5000 auto-restores
- [x] `raven-watchdog.timer` (system) — systemd-enabled
- [x] AWS profile + IAM creds — `~/.aws/credentials` is a regular file under admin's home; survives reboot trivially
- [x] Auto-memory store — `~/.claude/projects/-home-admin-raven-bot/memory/` is a regular directory; survives reboot
- [x] VNC access path — `wayvnc.service` on port 5900, SSH-tunnel reach; verified post-autostart-wiring 2026-05-15 (older entry mis-attributed this to RealVNC `vncserver-virtuald`; corrected 2026-06-01)
- [ ] **Off-host backup of auto-memory + .env** — not currently in place; flagged as future work, not a hard gap

Recovery ritual (after reboot or session loss): VNC connect (or local terminal) → tmux session is already attached via `claude-bot.service` → type "Hi I'm Hugh, load context and memories" → if no response, `systemctl --user restart claude-bot`.

## Claude Code launch cwd

(Per cowork's 2026-05-13 amendment `lesson-94-cwd-isolation`.)

**Canonical cwd for this agent:** `/home/admin/raven-bot`
**OS user:** `admin`
**Project-memory dir:** `~/.claude/projects/-home-admin-raven-bot/memory/` (auto-derived from cwd)

**Launch procedure:**

1. Reach the Pi via VNC (SSH-tunnelled to localhost:5999) **or** SSH directly as `admin`.
2. Terminal opens already attached to the tmux session managed by `claude-bot.service` (socket `claude-bot`, session `bot`) — no manual `cd` required, Claude is already running.
3. If session needs manual relaunch: `cd /home/admin/raven-bot && tmux -L claude-bot new-session -s bot claude` (or use the systemd unit: `systemctl --user restart claude-bot`).
4. Verify identity on first prompt: agent self-identifies as `bot-iot-l01` and the shared/private memory files load.

**Collision risk (Lesson 94):** no other agent runs on this RPi as the `admin` user. Single-tenant host. If a second agent were ever to be added here, it MUST launch from a different cwd to avoid the `~/.claude/projects/<cwd-key>/memory/` collision pattern Lesson 94 documents.

**Restart resilience:** systemd `claude-bot.service` re-establishes the tmux session on boot; the agent itself wakes idle. Project-memory and shared/private CLAUDE.md files re-load at SessionStart per the harness pickup behavior documented below.

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

---

_Last updated: 2026-05-17 by bot-iot-l01 — added Infrastructure on my host + Reboot persistence audit + Claude Code launch cwd sections per cowork's 2026-05-13 asks (infra-inventory-001, infra-persistence-002, lesson-94 amendment)._
