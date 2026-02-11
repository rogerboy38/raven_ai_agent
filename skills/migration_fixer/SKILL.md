---
name: migration-fixer
description: >
  FoxPro to ERPNext migration validation and repair.
  Trigger: When scanning, comparing, or fixing migration issues for quotations/sales orders.
license: MIT
metadata:
  author: AMB-Wellness
  version: "1.0"
  scope: [root, skills]
  auto_invoke:
    - "Scanning migration status"
    - "Fixing quotation data"
    - "Comparing FoxPro vs ERPNext"
    - "Generating migration reports"
  requires:
    doctypes: ["Quotation", "Sales Order"]
  folio_ranges:
    2024: {start: "00752", end: "00980"}
    2025: {start: "00980", end: "01160"}
allowed-tools: Read, Edit, Write, Bash
---

# Migration Fixer Skill

## CRITICAL RULES
- **ALWAYS** preview before applying fixes (`fix folio XXXXX` → `fix folio XXXXX confirm`)
- **NEVER** bulk apply without reviewing preview first
- **ALWAYS** verify FoxPro JSON source exists before attempting fix

## Migration Flow
```
FoxPro Invoice (JSON) → Quotation → Sales Order
                       (skipping Lead/Opportunity)
```

---

## Commands

### Scan Migration Status
```bash
scan migration 2024              # Scan year 2024 (00752-00980)
scan migration 2025              # Scan year 2025 (00980-01160)
scan migration from 00800 to 00850  # Custom range
```

### Compare Single Folio
```bash
compare folio 00752              # Side-by-side comparison
```

### Fix a Folio
```bash
fix folio 00752                  # Preview only (DRY RUN)
fix folio 00752 confirm          # Apply changes
```

### Generate Report
```bash
migration report                 # Full report
migration report 2024            # Year 2024 only
```

---

## Folio Ranges

| Year | Start | End | Count |
|------|-------|-----|-------|
| 2024 | 00752 | 00980 | ~228 |
| 2025 | 00980 | 01160 | ~180 |

---

## What Gets Validated

| Field | Comparison |
|-------|------------|
| Customer | Name matching (case-insensitive) |
| Date | Transaction date exact match |
| Total | Grand total with 1% tolerance |
| Lote Real | Custom field for batch tracking |
| Item Count | Number of line items |

---

## What Gets Fixed

1. `custom_lote_real` from FoxPro source
2. Customer (if exact match found in ERPNext)
3. Transaction date (if different)
4. All changes logged for audit

---

## Configuration

### site_config.json
```json
{
  "foxpro_json_path": "/home/frappe/foxpro_data"
}
```

### Expected JSON Structure
```json
{
  "folio": "00752",
  "lote_real": "L001",
  "customer": "Customer Name",
  "fecha": "2024-01-15",
  "total": 15000.00,
  "items": [{"item": "PROD001", "qty": 10, "rate": 1500}]
}
```

---

## API Reference

| Endpoint | Args | Description |
|----------|------|-------------|
| `scan_folios` | year, start_folio, end_folio | Scan range |
| `validate_folio` | invoice_folio | Validate one |
| `preview_fix` | invoice_folio | Dry run |
| `apply_fix` | invoice_folio | Apply fix |
| `compare_folio` | invoice_folio | Side-by-side |
| `get_migration_report` | year | Full report |

---

## Example Session

```
User: scan migration 2024
Agent: 📊 Migration Scan - 228 scanned, 180 OK, 35 warnings, 10 errors

User: compare folio 00760
Agent: 📋 FoxPro: lote_real='L045' | ERPNext: lote_real='None' ⚠️

User: fix folio 00760
Agent: 🔍 Preview: custom_lote_real: 'None' → 'L045'

User: fix folio 00760 confirm  
Agent: ✅ Fixed: custom_lote_real updated to 'L045'
```
