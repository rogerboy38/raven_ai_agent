"""
Formulation Orchestrator Skill
==============================

Main orchestrator skill that coordinates sub-agents for the formulation workflow.
Registered as a Skill for external invocation via SkillRouter.
"""

import frappe
from typing import Dict, Optional, Any
from datetime import datetime

from raven_ai_agent.skills.framework import SkillBase

from .messages import (
    AgentMessage,
    AgentChannel,
    AgentMessageType,
    WorkflowPhase,
    WorkflowState,
    MessageFactory
)

from .agents import (
    BatchSelectorAgent,
    TDSComplianceAgent,
    CostCalculatorAgent,
    OptimizationEngine,
    ReportGenerator
)


class FormulationOrchestratorSkill(SkillBase):
    """
    Main orchestrator skill that coordinates sub-agents for formulation workflows.
    
    Implements the hybrid approach from the spec:
    - Registered as a Skill for external invocation (Approach A)
    - Uses direct method calls internally (Approach B)
    
    Workflow Phases:
    1. Request Analysis (handled in _parse_request)
    2. Batch Selection (BatchSelectorAgent)
    3. TDS Compliance (TDSComplianceAgent)
    4. Cost Calculation (CostCalculatorAgent)
    5. Optimization (OptimizationEngine) - if needed
    6. Report Generation (ReportGenerator)
    """
    
    name = "formulation-orchestrator"
    description = "Orchestrates formulation workflow for Amb Wellness/TDS"
    emoji = "🧪"
    version = "1.0.0"
    priority = 80
    
    triggers = [
        "formulate", "formulation", "create formula",
        "batch selection", "select batches", "formular",
        "nueva formula", "formulacion", "mezcla"
    ]
    
    patterns = [
        r"(?:create|make|run)\s+formulation",
        r"(?:select|find)\s+batches?\s+for",
        r"formul(?:ate|ation)\s+(?:for|of)",
    ]
    
    def __init__(self, agent=None):
        super().__init__(agent)
        
        # Initialize communication channel
        self.channel = AgentChannel(source_agent="orchestrator")
        
        # Initialize sub-agents with shared channel
        self.batch_selector = BatchSelectorAgent(channel=self.channel)
        self.tds_compliance = TDSComplianceAgent(channel=self.channel)
        self.cost_calculator = CostCalculatorAgent(channel=self.channel)
        self.optimizer = OptimizationEngine(channel=self.channel)
        self.reporter = ReportGenerator(channel=self.channel)
        
        # Workflow tracking
        self._active_workflows: Dict[str, WorkflowState] = {}
    
    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        """
        Main entry point from SkillRouter.
        
        Args:
            query: User's query/command
            context: Session context
            
        Returns:
            Response dict with handled, response, confidence, data
        """
        context = context or {}
        
        try:
            # Parse request from query
            request = self._parse_request(query, context)
            
            if not request:
                return {
                    "handled": True,
                    "response": "Could not parse formulation request. Please provide item code and quantity.",
                    "confidence": 0.5,
                    "data": None
                }
            
            # Run the workflow
            result = self._run_workflow(request)
            
            return {
                "handled": True,
                "response": self._format_response(result),
                "confidence": 0.95,
                "data": result
            }
            
        except Exception as e:
            frappe.log_error(f"Orchestrator error: {e}", "FormulationOrchestratorSkill")
            return {
                "handled": True,
                "response": f"Error processing formulation request: {str(e)}",
                "confidence": 0.3,
                "data": {"error": str(e)}
            }
    
    def _parse_request(self, query: str, context: Dict) -> Optional[Dict]:
        """
        Parse a formulation request from query.
        
        Extracts:
        - item_code
        - quantity_required
        - warehouse
        - tds_requirements
        - customer (optional)
        - sales_order (optional)
        """
        import re
        
        request = {
            "raw_query": query,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Try to extract item code (ITEM_XXXXXXXXXX format or generic XXXX-XXXX format)
        item_match = re.search(r'(ITEM_\d{10}|[A-Z]+-[A-Z0-9]+)', query, re.IGNORECASE)
        if item_match:
            request["item_code"] = item_match.group(0).upper()
        
        # Try to extract product code (4 digits)
        product_match = re.search(r'(?:product|codigo|code)[:\s]*(\d{4})', query, re.IGNORECASE)
        if product_match:
            request["product_code"] = product_match.group(1)
        
        # Extract quantity
        qty_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:kg|kilos?|units?|piezas?)?', query, re.IGNORECASE)
        if qty_match:
            request["quantity_required"] = float(qty_match.group(1))
        
        # Default warehouse
        request["warehouse"] = context.get("warehouse", "FG to Sell Warehouse - AMB-W")
        
        # TDS requirements from context
        request["tds_requirements"] = context.get("tds_requirements", {})
        
        # Customer/Sales Order from context
        request["customer"] = context.get("customer")
        request["sales_order"] = context.get("sales_order")
        
        # Validate minimum requirements
        if not request.get("item_code") and not request.get("product_code"):
            return None
        
        return request
    
    def _run_workflow(self, request: Dict) -> Dict:
        """
        Execute the 6-phase formulation workflow.
        
        Args:
            request: Parsed request dict
            
        Returns:
            Complete workflow state with all phase results
        """
        # Create workflow state
        workflow = WorkflowState(request=request)
        self._active_workflows[workflow.workflow_id] = workflow
        
        # Update channel with workflow ID
        self.channel.workflow_id = workflow.workflow_id
        
        try:
            # Phase 1: Request Analysis (already done in _parse_request)
            workflow.update_phase(WorkflowPhase.REQUEST_ANALYSIS, {
                "parsed_request": request,
                "status": "completed"
            })
            
            # Phase 2: Batch Selection
            batch_result = self._execute_batch_selection(request, workflow)
            workflow.update_phase(WorkflowPhase.BATCH_SELECTION, batch_result)
            
            if not batch_result.get('selected_batches'):
                # No batches found - short circuit
                workflow.status = workflow.status.FAILED
                return workflow.to_dict()
            
            # Phase 3: TDS Compliance
            compliance_result = self._execute_tds_compliance(
                batch_result.get('selected_batches', []),
                request.get('tds_requirements', {}),
                workflow
            )
            workflow.update_phase(WorkflowPhase.TDS_COMPLIANCE, compliance_result)
            
            # Phase 4: Cost Calculation
            cost_result = self._execute_cost_calculation(
                batch_result.get('selected_batches', []),
                workflow
            )
            workflow.update_phase(WorkflowPhase.COST_CALCULATION, cost_result)
            
            # Phase 5: Optimization (if compliance failed)
            if not compliance_result.get('passed', True):
                optimization_result = self._execute_optimization(workflow)
                workflow.update_phase(WorkflowPhase.OPTIMIZATION, optimization_result)
            
            # Phase 6: Report Generation
            report_result = self._execute_report_generation(workflow)
            workflow.update_phase(WorkflowPhase.REPORT_GENERATION, report_result)
            
            workflow.status = workflow.status.COMPLETED
            
        except Exception as e:
            workflow.status = workflow.status.FAILED
            frappe.log_error(f"Workflow {workflow.workflow_id} failed: {e}", "FormulationOrchestrator")
        
        return workflow.to_dict()
    
    def _execute_batch_selection(self, request: Dict, workflow: WorkflowState) -> Dict:
        """Execute Phase 2: Batch Selection."""
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="batch_selector",
            action="select_batches",
            payload={
                "item_code": request.get("item_code"),
                "product_code": request.get("product_code"),
                "warehouse": request.get("warehouse"),
                "quantity_required": request.get("quantity_required", 0),
                "tds_spec": request.get("tds_requirements")
            },
            workflow_id=workflow.workflow_id,
            phase=WorkflowPhase.BATCH_SELECTION
        )
        
        response = self.batch_selector.handle_message(message)
        
        if response.success:
            return response.result
        else:
            return {"error": response.error_message, "selected_batches": []}
    
    def _execute_tds_compliance(
        self, 
        batches: list, 
        tds_requirements: Dict,
        workflow: WorkflowState
    ) -> Dict:
        """Execute Phase 3: TDS Compliance."""
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="tds_compliance",
            action="validate_compliance",
            payload={
                "batches": batches,
                "tds_requirements": tds_requirements
            },
            workflow_id=workflow.workflow_id,
            phase=WorkflowPhase.TDS_COMPLIANCE
        )
        
        response = self.tds_compliance.handle_message(message)
        
        if response.success:
            return response.result
        else:
            return {"error": response.error_message, "passed": False}
    
    def _execute_cost_calculation(self, batches: list, workflow: WorkflowState) -> Dict:
        """Execute Phase 4: Cost Calculation."""
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="cost_calculator",
            action="calculate_costs",
            payload={
                "batches": batches,
                "include_overhead": True
            },
            workflow_id=workflow.workflow_id,
            phase=WorkflowPhase.COST_CALCULATION
        )
        
        response = self.cost_calculator.handle_message(message)
        
        if response.success:
            return response.result
        else:
            return {"error": response.error_message, "total_cost": 0}
    
    def _execute_optimization(self, workflow: WorkflowState) -> Dict:
        """Execute Phase 5: Optimization."""
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="optimization_engine",
            action="suggest_alternatives",
            payload={
                "workflow_state": workflow.to_dict()
            },
            workflow_id=workflow.workflow_id,
            phase=WorkflowPhase.OPTIMIZATION
        )
        
        response = self.optimizer.handle_message(message)
        
        if response.success:
            return response.result
        else:
            return {"error": response.error_message, "recommendations": []}
    
    def _execute_report_generation(self, workflow: WorkflowState) -> Dict:
        """Execute Phase 6: Report Generation."""
        message = AgentMessage(
            source_agent="orchestrator",
            target_agent="report_generator",
            action="generate_report",
            payload={
                "workflow_state": workflow.to_dict(),
                "report_type": "full"
            },
            workflow_id=workflow.workflow_id,
            phase=WorkflowPhase.REPORT_GENERATION
        )
        
        response = self.reporter.handle_message(message)
        
        if response.success:
            return response.result
        else:
            return {"error": response.error_message}
    
    def _format_response(self, result: Dict) -> str:
        """Format workflow result for user response."""
        phases = result.get('phases', {})
        
        # Get the report text summary if available
        report = phases.get('report_generation', {})
        if report.get('text_summary'):
            return report['text_summary']
        
        # Fallback to basic summary
        batch_sel = phases.get('batch_selection', {})
        compliance = phases.get('compliance', {})
        costs = phases.get('costs', {})
        
        lines = [
            f"🧪 **Formulation Workflow Complete**",
            f"",
            f"📦 **Batches:** {len(batch_sel.get('selected_batches', []))} selected",
            f"📊 **Coverage:** {batch_sel.get('coverage_percent', 0):.1f}%",
        ]
        
        if compliance:
            status = "✅ PASS" if compliance.get('passed') else "❌ FAIL"
            lines.append(f"✅ **Compliance:** {status}")
        
        if costs:
            lines.append(f"💰 **Cost:** {costs.get('currency', 'MXN')} {costs.get('total_cost', 0):,.2f}")
        
        return "\n".join(lines)
    
    def get_workflow_status(self, workflow_id: str) -> Optional[Dict]:
        """Get status of a workflow."""
        workflow = self._active_workflows.get(workflow_id)
        if workflow:
            return workflow.to_dict()
        return None
    
    def list_active_workflows(self) -> list:
        """List all active workflows."""
        return [
            {
                "workflow_id": wf.workflow_id,
                "status": wf.status.value,
                "current_phase": wf.current_phase.value if wf.current_phase else None,
                "created_at": wf.created_at.isoformat()
            }
            for wf in self._active_workflows.values()
        ]


# Export for auto-discovery
SKILL_CLASS = FormulationOrchestratorSkill
