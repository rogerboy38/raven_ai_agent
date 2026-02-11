---
name: formulation-advisor
description: >
  Suggests optimal formulations from available warehouse inventory.
  Trigger: When asking about formulations, blending cuñetes, matching TDS specs.
license: MIT
metadata:
  author: AMB-Wellness
  version: "1.0"
  scope: [root, skills]
  auto_invoke:
    - "Suggesting formulations from inventory"
    - "Finding batches that match TDS"
    - "Blending cuñetes for target specs"
    - "Optimizing raw material selection"
  requires:
    doctypes: ["Item", "Batch", "Stock Ledger Entry", "Warehouse", "BOM"]
allowed-tools: Read, Edit, Write, Bash
---

# Formulation Advisor Skill

## CRITICAL RULES
- **ALWAYS** check batch expiry dates before suggesting
- **ALWAYS** verify stock availability in real-time
- **NEVER** suggest formulations without validating TDS compatibility
- **ALWAYS** prioritize FIFO (First In, First Out) when multiple batches qualify

## Use Case
```
Engineer: "De todos los cuñetes del almacén Materias Primas, 
          ¿cuáles pueden formar este TDS para el Item PROD-001?"
          
AI: Analyzes inventory → Matches specs → Suggests optimal blend
```

---

## Commands

| Command | Description |
|---------|-------------|
| `formulate <item> from <warehouse>` | Suggest formulation for item using warehouse stock |
| `match tds <spec> with inventory` | Find batches matching TDS specifications |
| `blend options for <item>` | Show all possible blend combinations |
| `check batch <batch_id> specs` | Get specifications of a specific batch |

---

## Data Model

### Batch Custom Fields (cuñetes)
```
custom_tds_value       # Total Dissolved Solids
custom_ph_level        # pH measurement
custom_viscosity       # Viscosity (cP)
custom_density         # Density (g/mL)
custom_purity          # Purity percentage
custom_color_index     # Color measurement
custom_moisture        # Moisture content %
custom_lote_proveedor  # Supplier lot number
```

### Item Specifications (target TDS)
```
custom_tds_min, custom_tds_max
custom_ph_min, custom_ph_max
custom_viscosity_min, custom_viscosity_max
```

---

## Algorithm

### 1. Inventory Query
```python
# Get available batches in warehouse
batches = frappe.get_all("Stock Ledger Entry",
    filters={"warehouse": warehouse, "item_code": raw_material},
    fields=["batch_no", "actual_qty"])
```

### 2. Spec Matching
```python
# Check if batch meets target specs
def matches_spec(batch, target_tds):
    return (target_tds.min <= batch.tds <= target_tds.max)
```

### 3. Optimization (Linear Blend)
```python
# For blending multiple batches to hit target
# Weighted average: target = Σ(qty_i × spec_i) / Σ(qty_i)
```

---

## Example Session

```
User: formulate CREMA-HIDRATANTE from Almacen-MP

Agent: 📦 Analyzing inventory in Almacen-MP...

Found 5 compatible batches:

| Batch | Item | TDS | pH | Qty | Expiry |
|-------|------|-----|-----|-----|--------|
| CU-001 | GLICERINA | 12.5 | 7.0 | 50L | 2026-06 |
| CU-002 | AGUA-DESMINERALIZADA | 0.5 | 6.8 | 200L | 2026-12 |
| CU-003 | EMULSIONANTE-A | 8.2 | 7.2 | 25L | 2026-03 |

📋 Suggested Formulation for CREMA-HIDRATANTE:
- GLICERINA (CU-001): 15L → TDS contribution: 3.75
- AGUA-DESMINERALIZADA (CU-002): 80L → TDS contribution: 0.4
- EMULSIONANTE-A (CU-003): 5L → TDS contribution: 0.41

✅ Final blend TDS: 4.56 (Target: 4.0-5.0) ✓
✅ Final pH: 6.95 (Target: 6.5-7.5) ✓
```

---

## API Endpoints

| Endpoint | Args | Description |
|----------|------|-------------|
| `get_warehouse_batches` | warehouse, item_code | List available batches |
| `get_batch_specs` | batch_no | Get batch specifications |
| `get_item_target_specs` | item_code | Get target TDS for item |
| `calculate_blend` | batches[], target | Optimize blend proportions |
| `suggest_formulation` | item_code, warehouse | Full formulation suggestion |

---

## Integration Points

### ERPNext DocTypes
- **Batch**: Extended with custom spec fields
- **Item**: Target specifications
- **Stock Ledger Entry**: Real-time inventory
- **BOM**: Formula templates
- **Stock Entry**: Material consumption

### Future: ML Enhancement
- Learn from historical formulations
- Predict optimal blends
- Quality prediction from batch specs
