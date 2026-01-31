---
name: migration-fixer
description: "FoxPro to ERPNext migration validation and repair. Scan, compare, and fix quotations/sales orders migrated from legacy FoxPro invoices."
metadata: {"raven":{"emoji":"🔧","requires":{"doctypes":["Quotation","Sales Order"]},"folio_ranges":{"2024":{"start":"00752","end":"00980"},"2025":{"start":"00980","end":"01160"}}}}
---

# Migration Fixer Skill

Validate and repair FoxPro → ERPNext migration issues for quotations and sales orders.

## Migration Flow
```
FoxPro Invoice (JSON) → Quotation → Sales Order
                       (skipping Lead/Opportunity)
```

## When to Use (Trigger Phrases)

Use this skill when user asks:
- "scan migration 2024"
- "scan migration from 00800 to 00900"
- "fix folio 00752"
- "compare folio 00752"
- "migration report"
- "check quotation 00800"
- "validate folio range"

## Quick Commands

### Scan Migration Status
```
scan migration 2024
scan migration 2025
scan migration from 00800 to 00850
```

### Compare Single Folio
```
compare folio 00752
```
Shows side-by-side FoxPro vs ERPNext data with differences highlighted.

### Fix a Folio
```
fix folio 00752          # Preview changes (dry run)
fix folio 00752 confirm  # Apply changes
```

### Generate Report
```
migration report
migration report 2024
migration report 2025
```

## Folio Ranges

| Year | Start | End | Count |
|------|-------|-----|-------|
| 2024 | 00752 | 00980 | ~228 |
| 2025 | 00980 | 01160 | ~180 |

## What Gets Validated

- **Customer**: Name matching between FoxPro and ERPNext
- **Date**: Transaction date comparison
- **Total**: Grand total with 1% tolerance
- **Lote Real**: Custom field for batch/lot tracking
- **Item Count**: Number of line items

## What Gets Fixed

When running `fix folio XXXXX confirm`:
1. Updates `custom_lote_real` from FoxPro source
2. Corrects customer if match found in ERPNext
3. Fixes transaction date if different
4. Logs all changes for audit trail

## API Endpoints

All endpoints are under `raven_ai_agent.skills.migration_fixer.api`:

| Endpoint | Description |
|----------|-------------|
| `scan_folios(year, start_folio, end_folio)` | Scan range for issues |
| `validate_folio(invoice_folio)` | Validate single folio |
| `preview_fix(invoice_folio)` | Preview changes (dry run) |
| `apply_fix(invoice_folio)` | Apply fixes |
| `bulk_preview(start, end)` | Preview bulk fixes |
| `bulk_apply(start, end)` | Apply bulk fixes |
| `compare_folio(invoice_folio)` | Side-by-side comparison |
| `get_migration_report(year)` | Generate status report |
| `get_foxpro_data(invoice_folio)` | Get raw FoxPro JSON |

## Configuration

Set FoxPro JSON path in `site_config.json`:
```json
{
  "foxpro_json_path": "/home/frappe/foxpro_data"
}
```

Expected JSON structure:
```json
{
  "folio": "00752",
  "lote_real": "L001",
  "customer": "Customer Name",
  "fecha": "2024-01-15",
  "total": 15000.00,
  "items": [
    {"item": "PROD001", "qty": 10, "rate": 1500}
  ]
}
```

## Example Conversation

**User:** scan migration 2024

**Agent:** 
📊 **Migration Scan Results**
- Scanned: 228
- ✅ OK: 180
- ⚠️ Warnings: 35
- ❌ Errors: 10
- 📭 Missing: 3

**Top Issues:**
- 00755: Total mismatch (5.2%): FoxPro=$12,500 vs ERPNext=$11,850
- 00760: Lote_real mismatch: FoxPro='L045' vs ERPNext='None'
...

**User:** fix folio 00760

**Agent:**
🔍 Preview for folio 00760:
  - custom_lote_real: 'None' → 'L045'

*Say 'fix folio 00760 confirm' to apply*

**User:** fix folio 00760 confirm

**Agent:**
✅ Fixed folio 00760:
  - custom_lote_real: 'None' → 'L045'
