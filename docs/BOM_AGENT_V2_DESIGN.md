# BOM Agent v2 — Design
2026-07-05 · raven team · Companion to E:\Claude\BOM-issues-finish-plan-2026-07-05.md
Implements the 9 requirements from the AMB BOM deep-research handoff.

## Ownership split (proposal)
| Side | Owns |
|---|---|
| **raven_ai_agent (us)** | Agent brain: routing, intent grammar EN/ES, FamilyResolver, HONESTY verification layer, `bom repair wo`, health v2, Golden-Number FEFO util, DoD JSON, dry-run/`!` discipline |
| **amb_w_tds (Node B)** | Track A: #78 0705/juice + 0303/0301 master templates, #79 label fix AT SOURCE, #81 0307 3-level re-model, parser family registration |

Key decoupling: our honesty layer **verifies row existence after every write call**, so #79
is neutralized agent-side immediately — amb's source fix remains right but non-urgent for safety.

## Principle → mechanism
1. **Honesty over optimism** — `_verify_created()`: after any execute (`!`), assert
   `frappe.db.exists("BOM Creator", name)` (or item-filtered). Pipeline says "Created" but no
   row → report **NOT CREATED** + pipeline transcript. Never trust labels; trust rows.
2. **Full family coverage** — `family.py` FamilyResolver: registry of 0227/0307/0303/0301/
   HIGHPOL/ACETYPOL/**0705** with keywords EN/ES (juice/jugo/concentrado→0705, powder/polvo,
   200:1, 30:1…) + `template_available` flag. juice resolves to **0705, not 0227**; a family
   with no template short-circuits BEFORE calling amb: explicit "no template registered (#78)"
   — never silent success, never a mis-mapped create.
3. **Multi-level fidelity** — creation stays delegated to amb templates (their #81). Our
   guard: post-create verification reports the generated tree depth; `bom inspect` shows
   multi-level explosion so a flat 0307 is visible at a glance. Self-reference (B008) and
   duplicate-default (B009) enforced in health + validate.
4. **Dry-run-first, draft-only, human-gated** — `bom plan …` = first-class dry-run command;
   `!` required for any write; BOM Formula writes: **refused entirely** until #77 workflow
   exists (checked live via `frappe.get_all("Workflow", document_type="BOM Formula")`).
5. **WO-repair** — `bom repair wo MFG-WO-XXXX`: probe (exists → docstatus==0 or REFUSE →
   bom_no state). Plan mode reports: broken link? candidate active BOM for production_item?
   or needs re-create via family template. `!` executes ONLY: re-point draft WO to an
   existing verified BOM (db.set_value), or create draft BOM Creator (then human !submit).
   Submitted/in-process WOs: hard refuse with reason.
6. **Real BOM health** — v2 adds: WOs whose bom_no doesn't exist (the #70 failure mode),
   draft WOs w/ cancelled BOMs, self-referencing BOMs, plus v1 checks (dup-default,
   inactive-default, stale drafts).
7. **Golden-Number FEFO** — `golden.py`: parse `{product4}{folio3}{year2}{plant1}` from
   item/batch codes; FEFO rank = (year, folio) ascending. `bom lots <ITEM>` lists batches in
   true production order; NEVER manufacturing_date (migration artifact).
8. **Idempotent + reversible** — every write path: exists-guards; every executed op appends a
   ```json DoD``` block: {op, target, before, after, verified, timestamp, actor} — machine-
   checkable evidence for the dev→vpt→prod gates.
9. **Bilingual** — ES triggers/patterns (salud bom, reparar wo/orden, crear bom desde tds,
   lotes, plan bom); replies carry ES key-lines on refusals/confirmations.

## Command grammar v2 (adds to v1)
| Command (EN / ES) | Mode | Handler |
|---|---|---|
| `bom plan <request>` / `plan bom` | read | amb dry-run, explicit |
| `bom repair wo <WO>` / `reparar wo` | plan; `!`=execute | repair flow §5 |
| `bom lots <ITEM>` / `lotes bom` | read | Golden-Number FEFO ranking |
| `bom health` (v2) / `salud bom` | read | adds WO/self-ref checks |
| `bom help` / `ayuda bom` | read | capability card |
| v1: inspect/status/issues/serial */validate/create-from-tds/simulate blend | unchanged + honesty layer |

## Non-goals (tracked elsewhere)
Templates & parser families (#78/#81, amb) · label fix at source (#79, amb) · BOM Formula
lifecycle (#77, amb C1) · solver/business rules (#82, C3-C4, needs Alicia/Raúl).

## Test matrix
FamilyResolver (juice→0705 no-template refusal; keywords EN/ES) · golden parse+rank ·
honesty NOT-CREATED on phantom success · repair guards (missing WO, submitted WO refused,
re-point verified) · health detects WO→missing-BOM · canaries for every new phrase.
