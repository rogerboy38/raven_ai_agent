# Formulation Orchestrator - Agent Communication Specification

## Document Purpose

This document defines how the **Formulation Orchestrator** (main agent) communicates with its **sub-agents** in the Raven AI Agent system for Amb Wellness / Amb TDS.

---

## 1. Current Architecture Analysis

### 1.1 Existing Components in `raven_ai_agent`

| Component | Location | Purpose |
|-----------|----------|--------|
| **SkillBase** | `skills/framework.py` | Abstract base class for all skills/agents |
| **SkillRegistry** | `skills/framework.py` | Auto-discovers and manages skills |
| **SkillRouter** | `skills/framework.py` | Routes queries to appropriate skills with learning |
| **SkillLearner** | `skills/framework.py` | Tracks patterns and improves routing over time |
| **MessageRouter** | `gateway/router.py` | Routes by intent (QUERY, COMMAND, WORKFLOW, SKILL) |
| **SessionManager** | `gateway/session_manager.py` | Manages conversation context |

### 1.2 Existing Skill Example: `formulation_advisor`

The repository already has a formulation-related skill at `skills/formulation_advisor/` with:
- `skill.py` - Extends `SkillBase`
- `advisor.py` - Business logic
- `SKILL.md` - Metadata and documentation

---

## 2. Communication Approaches

### 2.1 Approach A: Skill-Based Architecture (RECOMMENDED)

Each sub-agent becomes a **Skill** that the Orchestrator invokes via the SkillRouter.

```
FormulationOrchestratorSkill (main skill)
    ├── BatchSelectorSkill 
    ├── TDSComplianceSkill
    ├── CostCalculatorSkill
    ├── OptimizationEngineSkill
    └── ReportGeneratorSkill
```

**Communication Flow:**
```python
from raven_ai_agent.skills.framework import get_router

class FormulationOrchestratorSkill(SkillBase):
    def handle(self, query: str, context: Dict) -> Dict:
        router = get_router()
        
        # Invoke sub-agent
        result = router.route("@batch_selector select for ITEM-001", context)
        
        return result
```

**Pros:**
- Uses existing framework
- Auto-discovery of skills
- Built-in learning/routing
- Loose coupling

**Cons:**
- String-based routing (less type-safe)
- Overhead for simple calls

---

### 2.2 Approach B: Direct Method Invocation

Sub-agents as Python classes with direct method calls.

```python
class FormulationOrchestrator:
    def __init__(self):
        self.batch_selector = BatchSelectorAgent()
        self.tds_compliance = TDSComplianceAgent()
        self.cost_calculator = CostCalculatorAgent()
    
    def run_workflow(self, request: FormulationRequest) -> FormulationResult:
        # Phase 2: Batch Selection
        batches = self.batch_selector.select_batches(request.ingredients)
        
        # Phase 3: TDS Compliance
        compliance = self.tds_compliance.validate(batches)
        
        # Phase 4: Cost Calculation
        costs = self.cost_calculator.calculate(batches)
        
        return FormulationResult(batches, compliance, costs)
```

**Pros:**
- Type-safe
- Fast execution
- Easy debugging

**Cons:**
- Tight coupling
- No dynamic discovery

---

### 2.3 Approach C: Event-Driven / Message Queue (BEST FOR SCALE)

Using Frappe's background jobs and realtime events.

```python
import frappe
from frappe.utils.background_jobs import enqueue

class FormulationOrchestrator:
    def start_workflow(self, request_id: str):
        # Emit event for listeners
        frappe.publish_realtime(
            event="formulation_phase",
            message={
                "phase": "batch_selection",
                "request_id": request_id,
                "payload": {...}
            }
        )
        
        # Or use async queue
        enqueue(
            "raven_ai_agent.skills.batch_selector.process",
            request_id=request_id,
            queue="long"
        )
```

**Pros:**
- Scalable
- Non-blocking
- Can distribute across workers

**Cons:**
- More complex
- Harder to debug
- Need state management

---

## 3. RECOMMENDED: Hybrid Approach

**Best solution: Combine Approaches A + B**

```python
from raven_ai_agent.skills.framework import SkillBase
from typing import Dict, Optional

# Sub-agents as classes (Approach B)
from .agents.batch_selector import BatchSelectorAgent
from .agents.tds_compliance import TDSComplianceAgent
from .agents.cost_calculator import CostCalculatorAgent
from .agents.optimization_engine import OptimizationEngine
from .agents.report_generator import ReportGenerator


class FormulationOrchestratorSkill(SkillBase):
    """
    Main orchestrator skill that coordinates sub-agents.
    Registered as a Skill for external invocation (Approach A)
    but uses direct calls internally (Approach B).
    """
    
    name = "formulation-orchestrator"
    description = "Orchestrates formulation workflow for Amb Wellness/TDS"
    emoji = "🧪"
    priority = 80
    
    triggers = [
        "formulate", "formulation", "create formula",
        "nueva formula", "formulacion"
    ]
    
    def __init__(self, agent=None):
        super().__init__(agent)
        # Initialize sub-agents (direct references)
        self.batch_selector = BatchSelectorAgent()
        self.tds_compliance = TDSComplianceAgent()
        self.cost_calculator = CostCalculatorAgent()
        self.optimizer = OptimizationEngine()
        self.reporter = ReportGenerator()
    
    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        """Main entry point from SkillRouter."""
        # Parse request
        request = self._parse_request(query, context)
        
        # Run workflow phases
        result = self._run_workflow(request)
        
        return {
            "handled": True,
            "response": self._format_response(result),
            "confidence": 0.95,
            "data": result
        }
    
    def _run_workflow(self, request) -> Dict:
        """Execute the 6-phase workflow."""
        workflow_state = {"request": request, "phases": {}}
        
        # Phase 1: Request Analysis (handled in _parse_request)
        
        # Phase 2: Batch Selection
        workflow_state["phases"]["batch_selection"] = \
            self.batch_selector.select(request)
        
        # Phase 3: TDS Compliance
        workflow_state["phases"]["compliance"] = \
            self.tds_compliance.validate(
                workflow_state["phases"]["batch_selection"]
            )
        
        # Phase 4: Cost Calculation
        workflow_state["phases"]["costs"] = \
            self.cost_calculator.calculate(
                workflow_state["phases"]["batch_selection"]
            )
        
        # Phase 5: Optimization (if needed)
        if not workflow_state["phases"]["compliance"]["passed"]:
            workflow_state["phases"]["optimization"] = \
                self.optimizer.suggest_alternatives(workflow_state)
        
        # Phase 6: Report Generation
        workflow_state["phases"]["report"] = \
            self.reporter.generate(workflow_state)
        
        return workflow_state


# Export for auto-discovery
SKILL_CLASS = FormulationOrchestratorSkill
```

---

## 4. Inter-Agent Message Contract

### 4.1 Standard Message Format

```python
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum


class AgentMessageType(Enum):
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    STATUS = "status"


@dataclass
class AgentMessage:
    """Standard message format for inter-agent communication."""
    
    # Header
    message_id: str
    message_type: AgentMessageType
    timestamp: datetime
    
    # Routing
    source_agent: str
    target_agent: str
    
    # Payload
    action: str
    payload: Dict[str, Any]
    
    # Context
    workflow_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    
    # Response fields
    success: Optional[bool] = None
    error_message: Optional[str] = None
    result: Optional[Any] = None
```

### 4.2 Example Messages

**Orchestrator → Batch Selector:**
```json
{
    "message_id": "msg_001",
    "message_type": "request",
    "timestamp": "2026-02-03T14:00:00",
    "source_agent": "formulation_orchestrator",
    "target_agent": "batch_selector",
    "action": "select_batches",
    "payload": {
        "item_code": "CREMA-HIDRATANTE-001",
        "warehouse": "Almacen-MP",
        "quantity_required": 1000,
        "production_date": "2026-02-10"
    },
    "workflow_id": "wf_formulation_001"
}
```

**Batch Selector → Orchestrator:**
```json
{
    "message_id": "msg_002",
    "message_type": "response",
    "timestamp": "2026-02-03T14:00:01",
    "source_agent": "batch_selector",
    "target_agent": "formulation_orchestrator",
    "action": "select_batches",
    "parent_message_id": "msg_001",
    "workflow_id": "wf_formulation_001",
    "success": true,
    "result": {
        "selected_batches": [
            {
                "batch_no": "BATCH-2026-001",
                "item_code": "ALOE-VERA-GEL",
                "quantity": 500,
                "expiry_date": "2027-01-15",
                "coa_status": "approved"
            }
        ],
        "total_cost": 15000.00,
        "coverage": 100
    }
}
```

---

## 5. Implementation Folder Structure

```
raven_ai_agent/skills/
├── formulation_orchestrator/          # NEW - Main orchestrator
│   ├── SKILL.md                        # Skill metadata
│   ├── __init__.py
│   ├── skill.py                        # FormulationOrchestratorSkill
│   ├── orchestrator.py                 # Workflow logic
│   ├── messages.py                     # AgentMessage definitions
│   └── agents/                         # Sub-agent implementations
│       ├── __init__.py
│       ├── base.py                     # BaseSubAgent class
│       ├── batch_selector.py           # Phase 2
│       ├── tds_compliance.py           # Phase 3
│       ├── cost_calculator.py          # Phase 4
│       ├── optimization_engine.py      # Phase 5
│       └── report_generator.py         # Phase 6
├── formulation_advisor/                # EXISTING
└── formulation_reader/                 # EXISTING
```

---

## 6. Next Steps

### Immediate Actions
1. [ ] Create `formulation_orchestrator` skill folder
2. [ ] Implement `messages.py` with AgentMessage class
3. [ ] Create `BaseSubAgent` class for common functionality
4. [ ] Implement each sub-agent (Phases 2-6)
5. [ ] Register skill for auto-discovery

### Testing
1. [ ] Unit tests for each sub-agent
2. [ ] Integration test for full workflow
3. [ ] Test via Raven chat interface

---

## 7. Version History

| Version | Date | Author | Changes |
|---------|------|--------|--------|
| 1.0 | 2026-02-03 | AI Orchestrator | Initial specification |

---

*This document serves as the communication protocol between the Formulation Orchestrator and its sub-agents in the Raven AI Agent system.*
