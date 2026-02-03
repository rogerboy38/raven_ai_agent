# IMPLEMENTATION ROADMAP: Aloe Powder Batch Optimization System

## Date: February 3, 2026
## Approach: HYBRID (raven_ai_agent + amb_w_tds)

================================================================================

## ✅ COMPLETED

1. **Technical Specifications (6 Phases)**
   - Phase 1: FORMULATION_READER_AGENT
   - Phase 2: BATCH_SELECTOR_AGENT
   - Phase 3: TDS_COMPLIANCE_CHECKER
   - Phase 4: COST_CALCULATOR
   - Phase 5: OPTIMIZATION_ENGINE
   - Phase 6: REPORT_GENERATOR

2. **Repository Analysis**
   - rnd_nutrition2: RavenTool patterns
   - raven_ai_agent: Full AI framework ✅ SELECTED PRIMARY
   - amb_w_tds: ERPNext doctypes ✅ SELECTED SECONDARY

3. **Existing Infrastructure Found**
   - formulation_advisor skill already exists in raven_ai_agent
   - SkillBase framework with auto-discovery
   - Multi-provider LLM support
   - Batch, COA, TDS doctypes in amb_w_tds

================================================================================

## 🔄 NEXT STEPS TO IMPLEMENT

### STEP 1: Clone and Setup
```bash
# Clone the primary repository
git clone https://github.com/rogerboy38/raven_ai_agent.git
cd raven_ai_agent

# Install dependencies
pip install -e .

# Add amb_w_tds as dependency (in pyproject.toml or requirements.txt)
```

### STEP 2: Create Skill Folders
```bash
cd raven_ai_agent/skills/

# Create 5 new skill folders (formulation_advisor already exists)
mkdir -p batch_selector
mkdir -p tds_compliance
mkdir -p cost_calculator
mkdir -p optimization_engine
mkdir -p report_generator
```

### STEP 3: Create Files in Each Skill Folder

Each skill needs 4 files following the formulation_advisor pattern:

```
batch_selector/
  __init__.py          # Export SKILL_CLASS
  SKILL.md             # Documentation
  skill.py             # SkillBase implementation
  selector.py          # Core business logic
```

### STEP 4: Skill Implementation Pattern

All skills follow this structure:

#### __init__.py
```python
from .skill import [SkillName]Skill
__all__ = ['[SkillName]Skill']
```

#### skill.py Structure
```python
from ..framework import SkillBase
from .[logic_file] import [LogicClass]

class [SkillName]Skill(SkillBase):
    name = "skill-name"
    description = "What it does"
    emoji = "🔧"
    version = "1.0.0"
    priority = 50
    
    triggers = ["keyword1", "keyword2"]
    patterns = [r"regex_pattern"]
    
    def __init__(self, agent=None):
        super().__init__(agent)
        self.logic = [LogicClass]()
    
    def handle(self, query: str, context: Dict = None):
        # Parse query
        # Call logic layer
        # Return {handled, response, confidence, data}
        pass

SKILL_CLASS = [SkillName]Skill
```

================================================================================

## 📋 SKILLS TO CREATE

### Skill 2: batch_selector
**Purpose**: Sort batches by Golden number + FEFO  
**Key Methods**:
- `get_batches_for_item(item_code, golden_number, warehouse)`
- `_sort_batches()` - Golden priority then FEFO
- `_extract_golden_from_batch(batch_id)`

**ERPNext Queries**:
- Batch doctype for batch info
- Bin doctype for actual stock quantities

---

### Skill 3: tds_compliance
**Purpose**: Validate batches against TDS specifications  
**Key Methods**:
- `check_compliance(item_code, batch_list)`
- `_get_coa_data(batch_id)` - Query COA AMB/AMB2
- `_validate_parameters(coa, tds_specs)`

**ERPNext Queries**:
- COA AMB / COA AMB2 doctypes
- TDS specifications from Item

---

### Skill 4: cost_calculator
**Purpose**: Calculate pricing for batches  
**Key Methods**:
- `get_batch_prices(item_code, batch_list)`
- `_get_item_price(item_code, batch_id)`
- Fallback: standard_rate → last_purchase_rate

**ERPNext Queries**:
- Item Price doctype
- Item.standard_rate
- Purchase Receipt for last_purchase_rate

---

### Skill 5: optimization_engine
**Purpose**: Optimize batch allocation for cost  
**Key Methods**:
- `optimize_allocation(batches, required_qty, strategy)`
- `_calculate_fefo_cost(batches, qty)`
- `_generate_what_if_scenarios(batches, qty)`
- `_calculate_savings(original, optimized)`

**Algorithm**:
1. FEFO allocation
2. Check single vs multi-batch with tolerance
3. Generate scenarios (FEFO, LOWEST_COST, BALANCED)
4. Calculate savings

---

### Skill 6: report_generator
**Purpose**: Create final optimization reports  
**Key Methods**:
- `generate_report(optimization_result, format)`
- `_build_text_report()` - Human-readable ASCII
- `_build_json_export()` - Machine-readable
- `_generate_recommendations()`

**Output Formats**:
- Text with ASCII tables
- JSON for API integration
- Recommendations based on status

================================================================================

## 🎯 TESTING STRATEGY

### Unit Tests
Create `tests/test_[skill_name].py` for each skill:
- Test batch sorting logic
- Test COA validation
- Test cost calculations
- Test optimization algorithms
- Test report generation

### Integration Tests
Test full pipeline:
1. User query → FormulationAdvisor
2. BatchSelector → get sorted batches
3. TDSCompliance → validate batches
4. CostCalculator → add pricing
5. OptimizationEngine → optimize selection
6. ReportGenerator → create report

### Test Data
Use amb_w_tds fixtures:
- Sample batches with expiry dates
- COA data with parameters
- Item prices
- Expected optimization results

================================================================================

## 📦 DEPLOYMENT

### Option 1: Frappe Bench (Recommended)
```bash
# In your Frappe bench
cd apps
git clone https://github.com/rogerboy38/raven_ai_agent.git
bench --site [your-site] install-app raven_ai_agent

# Skills are auto-discovered on startup
```

### Option 2: Standalone
```bash
# Run as standalone service
python -m raven_ai_agent.api.app

# Access via http://localhost:8000
```

================================================================================

## 🚀 USAGE EXAMPLES

Once deployed, users can interact via:

### Chat Interface
```
User: "Optimize 150kg of POLVO-ALOE-200X-TAN"

Orchestrator:
→ FormulationAdvisor extracts: item=POLVO-ALOE-200X-TAN, qty=150, golden=2311
→ BatchSelector finds 5 batches, sorts by golden 2311 + FEFO
→ TDSCompliance validates all 5 batches against COA
→ CostCalculator adds pricing from Item Price
→ OptimizationEngine optimizes allocation, saves $625 (5%)
→ ReportGenerator creates final report

Bot: "✅ Optimization complete! Using 2 batches (BATCH-2311-001: 100kg, 
BATCH-2311-002: 50kg). Savings: $625 (5%). Full report attached."
```

### API Endpoint
```bash
curl -X POST http://localhost:8000/api/skills/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "item_code": "POLVO-ALOE-200X-TAN",
    "required_qty": 150,
    "warehouse": "Stores - AMB"
  }'
```

================================================================================

## 📚 DOCUMENTATION LINKS

- **Technical Specs**: See Phase 1-6 documents in Google Docs
- **raven_ai_agent**: https://github.com/rogerboy38/raven_ai_agent
- **amb_w_tds**: https://github.com/rogerboy38/amb_w_tds
- **ERPNext Batch**: https://docs.erpnext.com/docs/user/manual/en/stock/batch
- **ERPNext Item**: https://docs.erpnext.com/docs/user/manual/en/stock/item

================================================================================

## ✉️ CONTACT & SUPPORT

- Repository Owner: rogerboy38
- Location: Torreón, Coahuila, Mexico
- ERPNext Site: [Your Frappe Cloud instance]

================================================================================

READY TO START IMPLEMENTATION!

