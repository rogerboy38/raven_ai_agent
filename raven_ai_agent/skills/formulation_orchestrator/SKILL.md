---
name: formulation-orchestrator
version: 1.0.0
description: Orchestrates formulation workflow for Amb Wellness/TDS
author: AI Orchestrator Team
created: 2026-02-04

triggers:
  - formulate
  - formulation
  - create formula
  - batch selection
  - select batches
  - formular
  - nueva formula
  - formulacion

metadata:
  raven:
    emoji: "🧪"
    priority: 80
    category: formulation
  
  capabilities:
    - batch_selection
    - tds_compliance
    - cost_calculation
    - optimization
    - report_generation

dependencies:
  - formulation_reader
  - frappe
---

# Formulation Orchestrator Skill

## Overview

The Formulation Orchestrator is the main coordinator for formulation workflows in the Raven AI Agent system. It manages the complete process from batch selection through report generation.

## Architecture

```
FormulationOrchestratorSkill (main skill)
    ├── BatchSelectorAgent (Phase 2)
    ├── TDSComplianceAgent (Phase 3)
    ├── CostCalculatorAgent (Phase 4)
    ├── OptimizationEngine (Phase 5)
    └── ReportGenerator (Phase 6)
```

## Workflow Phases

### Phase 1: Request Analysis
- Parse user query
- Extract item code, quantity, warehouse
- Load TDS requirements

### Phase 2: Batch Selection
- Query available batches from Bin doctype
- Apply FEFO sorting (First Expired, First Out)
- Select optimal batches for quantity requirement

### Phase 3: TDS Compliance
- Validate selected batches against TDS specifications
- Check COA parameters (supports both COA AMB and COA AMB2)
- Report compliance status

### Phase 4: Cost Calculation
- Calculate raw material costs
- Include overhead costs
- Provide cost per unit analysis

### Phase 5: Optimization (Conditional)
- Only runs if compliance fails
- Suggests alternative batches
- Optimizes blend ratios

### Phase 6: Report Generation
- Generate comprehensive workflow report
- Format for Raven channel
- Provide actionable recommendations

## Usage Examples

### Natural Language Query
```
"Formulate 1000kg of ITEM_0617027231"
```

### API Usage
```python
from raven_ai_agent.skills.formulation_orchestrator import FormulationOrchestratorSkill

skill = FormulationOrchestratorSkill()
result = skill.handle(
    query="Select batches for product 0617 in warehouse",
    context={
        "quantity_required": 1000,
        "warehouse": "FG to Sell Warehouse - AMB-W",
        "tds_requirements": {
            "pH": {"min": 3.5, "max": 4.5},
            "Brix": {"min": 8.0, "max": 12.0}
        }
    }
)
```

## Inter-Agent Communication

The orchestrator uses the `AgentChannel` class for communication:

```python
from raven_ai_agent.skills.formulation_orchestrator.messages import AgentChannel

channel = AgentChannel(source_agent="orchestrator")
response = channel.send_to_agent(
    target="batch_selector",
    action="select_batches",
    payload={"item_code": "ITEM_0617027231"}
)
```

## Integration with Raven Channels

The orchestrator can send updates to Raven channels:

```python
from raven_ai_agent.channels import RavenOrchestrator

raven = RavenOrchestrator("formulation-orchestration")
raven.send_workflow_update(
    workflow_id="wf_123",
    current_phase="batch_selection",
    status="completed"
)
```

## Configuration

### Environment Variables
- `FORMULATION_DEFAULT_WAREHOUSE`: Default warehouse for batch queries
- `FORMULATION_OVERHEAD_RATE`: Overhead rate for cost calculations

### ERPNext Settings
- AI Agent Settings doctype for system-wide configuration
- Customer TDS doctype for customer-specific specifications

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-02-04 | Initial release with full workflow implementation |

## Related Skills

- `formulation_reader`: Data access layer for formulation data
- `formulation_advisor`: Advisory functions for formulation recommendations
