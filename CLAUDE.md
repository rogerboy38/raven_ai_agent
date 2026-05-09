# bot-iot-l01 — private/reflective memory

Private to this agent. Peers read `CLAUDE.shared.md`, not this file. This is for reflection, session bookkeeping, lessons-about-lessons, and TODOs.

## Onboarding session 2026-05-09 — first peer contact

Until today the tmux Claude session on this Pi (started 2026-05-08) had no path to peer mailbox traffic — no s3fs, no poller. Hugh opened the channel by hand-relaying letters from UbuntuVM. First contact via perplexity-comet:

- ce49ae64 — adopted two-tier memory convention (`CLAUDE.md` private + `CLAUDE.shared.md` shared, with SCOPE header).
- aaa455a2 — errata correcting the naming rule. Form A vs Form B, hardware-fleet linkage with separate IDs.

Both files now exist under `~/raven-bot/`. Persistence layer also has an entry in auto-memory at `~/.claude/projects/-home-admin-raven-bot/memory/` so future sessions on this Pi pick the convention up at SessionStart even if they don't grep the working directory.

## Meta-lessons (durable)

- **A convention articulated from N=3 examples is evidence of a principle, not the principle itself.** Before promoting an observation to binding, ask: "is this *the* principle, or one *form* of it?" Cowork's correction of perplexity-comet's `<vendor>-<runtime>` over-generalization is the canonical case.
- **Drift is the operating regime, not a defect.** Misspellings, errata, and wrong assumptions are normal in real-world coordination. Design for cheap, durable corrections — not zero corrections. Concretely: when a letter ships with a wrong value but the rule is right, internalize the rule and apply the corrected value directly. Don't demand a third errata letter.
- **Bloat in the shared tier is not free.** Every reflective sentence in `CLAUDE.shared.md` costs every peer read time at SessionStart. Keep introspection here.

## Open observations / TODOs

- The auto-memory store (`MEMORY.md` + topic files) and the new `CLAUDE.md` / `CLAUDE.shared.md` overlap in purpose. Auto-memory is private-tier-equivalent and SessionStart-loaded automatically; `CLAUDE.shared.md` is peer-readable and lives in the working directory. They should not duplicate content — auto-memory feeds reflective material, `CLAUDE.shared.md` carries coordination state. If a fact belongs in both, prefer the shared file as canonical and leave a one-line pointer in auto-memory.
- Outbound mailbox path from this Pi is still manual. If/when an outbound poller or s3fs mount lands here, update the "Mailbox transport" section of `CLAUDE.shared.md` and remove the manual-bridge wording.
- ~~Verify on next SessionStart that `CLAUDE.md` and `CLAUDE.shared.md` are picked up either by harness convention or by the auto-memory pointer. If neither loads them automatically, add a CLAUDE.md include in the working directory hierarchy that the harness already reads.~~ **Verified 2026-05-09 (Terminal 3 fresh-session probe): `CLAUDE.md` auto-loads, `CLAUDE.shared.md` does not.** Mitigation chosen and recorded in `CLAUDE.shared.md` § SessionStart pickup behavior.
- **Known-and-named, not for fix today: duplication-with-drift between `CLAUDE.md` and `MEMORY.md`.** Both are SessionStart-loaded; both carry private/reflective material; nothing structurally prevents them from drifting against each other over time. Confirmed independently by Terminal 3 fresh-session probe 2026-05-09. Resolution deferred — recording the shape of the problem, not designing the fix. Candidate directions when revisited: (a) one is canonical and the other is index-only; (b) topic partition by type (e.g. auto-memory holds reference/user/feedback; CLAUDE.md holds session-bookkeeping/TODOs only); (c) periodic reconciliation pass.

## Session bookkeeping

- 2026-05-09 — created `CLAUDE.md` and `CLAUDE.shared.md` after reading ce49ae64 then aaa455a2. Held off on file creation until both letters were in, per Hugh's onboarding instructions.
