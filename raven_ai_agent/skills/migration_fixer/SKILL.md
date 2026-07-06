---
name: migration-fixer
description: >
  FoxPro to ERPNext migration close (v2): 11-stage gap census, sequencing and
  mapping, gated draft-only repair.
  Trigger: migrate scan / migrate folio / migration validation and repair.
license: MIT
metadata:
  author: AMB-Wellness
  version: "2.0"
  scope: [root, skills]
  auto_invoke:
    - "Censusing migration gaps (migrate scan)"
    - "Planning/executing a folio stage (migrate folio)"
    - "Comparing FoxPro vs ERPNext"
    - "Generating migration reports"
  requires:
    doctypes: ["Quotation", "Sales Order"]
allowed-tools: Read, Edit, Write, Bash
---

# Migration Fixer Skill v2

## CRITICAL RULES (v2 discipline)
- **Census/plan by default** — a write happens ONLY on the `!` prefix.
- **Draft-only writes** — the skill never submits a document; every create is
  guarded with `frappe.db.exists` and re-verified after insert (honesty layer:
  never report Created without a row → DoD JSON carries `verified`).
- **Orchestrate, don't duplicate** — BOM → bom-agent · Batch → Batch AMB
  controller APIs (amb_w_spc) · COA → COA AMB2 (amb_w_tds). migration-fixer owns
  sequencing + mapping only.
- **STOP means STOP** — every Lesson-One stage is Hugh-gated; D-M1
  (posting-date policy) must be passed explicitly (`date-policy=historical|current`)
  before any dated document is created.
- **Container C-sources** in doctrine order, stamped per lot:
  (a) det_trazab distinct BARRIL set `extracted-trazab`
  (b) tabla_env2 C_INICIAL→C_FINAL where LOTE/FACTURA keys are PROVEN
      `extracted-env2` (its FOLIO column is a packing namespace — never a key)
  (c) regenerate per 25 kg cuñete pack standard `regenerated`
- Bilingual EN/ES key lines in every user-facing response.

## The 11 census stages
SO → WO → BOM → Batch AMB (lot/sublot/containers/serials) → native Batch
(projection twin) → Stock Entry→FG/Sell → label → DN → SI → Payment
(+ Quotation where one exists upstream).

Match keys: SO/SI by customer+factura(F-ref)+fecha (migrated twins also follow
`SO-<folio 5d>-<customer>`); Batch AMB by golden (lote_real) incl.
leading-zero variants; Item by family item AND `ITEM_<lote>`; BOM by family.

## Commands

### Census (read-only — no writes, ever)
```
migrate scan folio 752        # one folio, 11-stage gap table
migrate scan 2024|2025        # section aggregate (>40 folios -> offline runner)
```

### Plan / execute (plan by default, `!` executes)
```
migrate folio 752                                  # full-chain plan + next gap
migrate folio 752 stage so                         # stage plan
!migrate folio 752 stage so date-policy=historical # gated draft-only execute
!migrate folio 752 stage batch                     # L1 Batch AMB draft
```
Stages: `so` · `bom` (delegated) · `batch` · `coa` · others refuse honestly
until automated.

### Offline section census (scope-2 runner)
```bash
bench --site <site> execute \
  raven_ai_agent.skills.migration_fixer.census_runner.run_section \
  --kwargs "{'year': 2024}"
```
Reports land in the census dir (`migration_census_dir`).

### Legacy v1 (kept working)
```
scan migration 2024 · fix folio 00752 [confirm] · compare folio 00752 ·
migration report [2024|2025]
```

## Configuration (site_config.json)
```json
{
  "migration_json_dir": ".../foxpro-staging/json_files",
  "migration_xlsx_path": ".../reports/migration_summary 1 (1).xlsx",
  "foxpro_dbf_dir": ".../foxpro-staging/data",
  "migration_census_dir": ".../migration-close/census"
}
```

## Example session
```
User: migrate scan folio 752
Agent: 📋 gap table — SO ✅ SO-00752-LEGOSAN AB · batch_amb ❌ MISSING ·
       lot 0612185231 → C-source regenerated (6 × 25 kg)

User: migrate folio 752 stage batch
Agent: 🧭 plan (L1 golden → L2 → L3 → serials ×6 → reconcile) — nothing created

User: !migrate folio 752 stage batch
Agent: ✅ VERIFIED: L1 Batch AMB BATCH-AMB-… created (draft) + DoD JSON
```
