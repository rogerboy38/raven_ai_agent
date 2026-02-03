---
name: formulation-reader
description: >
  Read-only formulation data reader for aloe powder formulation.
  Reads Batch AMB, COA AMB2, Item TDS, and Sales Order data from ERPNext.
  Computes weighted averages for blend simulations without modifying any data.
  Trigger: When reading formulation data, simulating blends, checking TDS specs.
license: MIT
metadata:
  author: AMB-Wellness
  version: "1.0.0"
  scope: [root, skills, formulation]
  auto_invoke:
    - "Reading batch data"
    - "Simulating blend"
    - "Checking TDS specifications"
    - "Getting COA parameters"
    - "Analyzing formulation"
allowed-tools: Read
---

# Formulation Reader

**Phase 1 Skill: Data Model & Read-Only Analytics**

## CRITICAL RULES
- **ALWAYS** read-only: Never modify ERPNext data
- **ALWAYS** validate batch existence before reading COA
- **ALWAYS** return calculations with source data for traceability
- **NEVER** create, update, or delete any ERPNext documents

---

## System Prompt

> You are a formulation reader agent for aloe powder formulation.
> You receive item code, warehouse, and batch identifiers.
> You read data from ERPNext doctypes: Batch AMB, COA AMB2, Item, Sales Order.
> You compute weighted averages for blend simulations.
> You never modify ERPNext data; you only return data and calculations.

---

## Capabilities

### 1. Read TDS Specifications
Retrieve Technical Data Sheet (TDS) parameters for a Sales Order item.

**Function:** `get_tds_for_sales_order_item(so_name, item_code)`

**Returns:**
- TDS parameter ranges (min, max, nominal)
- Customer-specific specifications
- Item default specifications

### 2. Read Batch Data
Get all Batch AMB records for an item in a specific warehouse.

**Function:** `get_batches_for_item_and_warehouse(item_code, warehouse)`

**Returns:**
- List of Batch AMB records
- Cunete details (containers, kilos available)
- Manufacturing dates and WWDYY codes
- Subproduct codes (0301-0304)

### 3. Read COA Parameters
Get internal COA (COA AMB2) analytical parameters for a batch.

**Function:** `get_coa_amb2_for_batch(batch_amb_name)`

**Returns:**
- All analytical parameters (pH, polysaccharides, ash, color, etc.)
- Measured values and averages
- PASS/FAIL status against TDS

### 4. Simulate Blend
Compute weighted averages for a proposed blend without creating any documents.

**Function:** `simulate_blend(blend_inputs)`

**Input:**
```python
blend_inputs = [
    {"cunete_id": "BATCH-001-C1", "mass_kg": 10.0},
    {"cunete_id": "BATCH-002-C1", "mass_kg": 15.0}
]
target_item = "AL-QX-90-10"
```

**Returns:**
- Predicted values for each parameter
- Comparison against TDS ranges
- PASS/FAIL status for each parameter
- Total mass and weighted calculation details

---

## Data Model Mappings

### Batch AMB Fields
| JSON Field | Description |
|------------|-------------|
| `product` | Main product code (e.g., 0227) |
| `subproduct` | Subproduct code (0301-0304) |
| `lot` | Lot identifier |
| `sublot` | Sublot identifier |
| `containers` | Container serials per cunete |
| `kilos` | Total kilos available |
| `brix` | BRIX measured on production floor |
| `total_solids` | Total solids measured in lab |

### Subproduct Codes
| Code | Description |
|------|-------------|
| 0227-0301 | Permeate |
| 0227-0302 | Retentate |
| 0227-0303 | Normal |
| 0227-0304 | Puntas, colas y raspaduras (scrap) |

### COA AMB2 Fields
| Field | Description |
|-------|-------------|
| `parameter_code` | Parameter identifier |
| `nominal_value` | Expected/target value |
| `min_value` | Minimum acceptable value |
| `max_value` | Maximum acceptable value |
| `average` | Calculated average of measurements |
| `result` | PASS/FAIL status |

---

## Weighted Average Formula

```
Final_value = SUM(wi × value_i) / SUM(wi)
```

Where `wi` is the mass (kg) taken from cunete `i`.

---

## Example Queries

### Read batch data
```
"Show all batches for item 0227-0303 in warehouse Almacen-MP"
```

### Read COA for batch
```
"Get COA parameters for batch BATCH-AMB-2024-001"
```

### Simulate blend
```
"Simulate a blend of 10 kg from batch X cunete 1 and 15 kg from batch Y cunete 2 
for item AL-QX-90-10. Show predicted pH, polysaccharides, ash versus TDS."
```

### Get TDS for order
```
"What are the TDS specifications for item AL-QX-90-10 in Sales Order SO-00754?"
```

---

## Test Cases (Phase 1)

| ID | Description | Verification |
|----|-------------|--------------|
| TC1.1 | Read Batch AMB list for item X in warehouse Y | Verify count and fields returned |
| TC1.2 | Read COA AMB2 parameters for a known batch | Verify all analytics returned |
| TC1.3 | Simulate blend with 2 cunetes | Verify weighted average calculation |
| TC1.4 | Compare simulation result to TDS | Verify PASS/FAIL flags |

---

## Dependencies

- `frappe` framework
- `amb_w_tds` app (Batch AMB, COA AMB, COA AMB2 doctypes)
- ERPNext (Item, Sales Order doctypes)
