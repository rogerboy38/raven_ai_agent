"""
Optimization Engine Agent - Phase 5
====================================

Suggests alternative batch selections when TDS compliance fails.
"""

import frappe
from typing import Dict, List, Any, Optional

from .base import BaseSubAgent
from ..messages import AgentMessage, WorkflowPhase, AgentChannel

from ...formulation_reader.reader import (
    get_available_batches,
    get_batch_coa_parameters,
    check_tds_compliance,
    parse_golden_number
)


class OptimizationEngine(BaseSubAgent):
    """
    Optimization Engine (Phase 5 of workflow).
    
    Responsibilities:
    - Suggest alternative batches when TDS fails
    - Optimize blend ratios for target specifications
    - Minimize cost while meeting quality requirements
    - Provide multiple optimization scenarios
    """
    
    name = "optimization_engine"
    description = "Batch and blend optimization"
    emoji = "⚡"
    phase = WorkflowPhase.OPTIMIZATION
    
    def process(self, action: str, payload: Dict, message: AgentMessage) -> Optional[Dict]:
        """Route to specific action handler."""
        actions = {
            "optimize": self._optimize,
            "suggest_alternatives": self._suggest_alternatives,
            "optimize_blend": self._optimize_blend,
            "find_compliant_batches": self._find_compliant_batches,
        }
        
        handler = actions.get(action)
        if handler:
            return handler(payload, message)
        return None
    
    def _optimize(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Main optimization action - analyze workflow state and suggest improvements.
        
        Args (in payload):
            workflow_state: Current workflow state with phase results
            constraints: Optimization constraints {max_batches, max_cost, etc.}
            
        Returns:
            Dict with optimized selection and recommendations
        """
        workflow_state = payload.get('workflow_state', {})
        constraints = payload.get('constraints', {})
        
        self._log("Running optimization analysis")
        self.send_status("optimizing", {"constraints": list(constraints.keys())})
        
        # Analyze current state
        batch_selection = workflow_state.get('phases', {}).get('batch_selection', {})
        compliance = workflow_state.get('phases', {}).get('compliance', {})
        
        recommendations = []
        optimized_selection = None
        
        # Check if compliance failed
        if compliance and not compliance.get('passed', True):
            # Find alternatives for non-compliant batches
            non_compliant = compliance.get('non_compliant_batches', [])
            tds_requirements = payload.get('tds_requirements', {})
            
            for batch in non_compliant:
                alternatives = self._find_alternatives_for_batch(
                    batch,
                    tds_requirements,
                    constraints
                )
                
                if alternatives:
                    recommendations.append({
                        "type": "replace_batch",
                        "original_batch": batch.get('batch_name'),
                        "alternatives": alternatives,
                        "reason": f"Non-compliant on: {', '.join(batch.get('failing_parameters', []))}"
                    })
        
        # Cost optimization
        if constraints.get('minimize_cost'):
            cost_optimization = self._optimize_for_cost(
                batch_selection.get('selected_batches', []),
                constraints
            )
            if cost_optimization:
                recommendations.append({
                    "type": "cost_optimization",
                    "potential_savings": cost_optimization.get('savings', 0),
                    "suggested_changes": cost_optimization.get('changes', [])
                })
        
        self.send_status("completed", {"recommendations": len(recommendations)})
        
        return {
            "recommendations": recommendations,
            "optimized_selection": optimized_selection,
            "optimization_applied": len(recommendations) > 0,
            "summary": f"Generated {len(recommendations)} optimization recommendations"
        }
    
    def _suggest_alternatives(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Suggest alternative batches for current selection.
        
        Args (in payload):
            workflow_state: Current workflow state
            
        Returns:
            Dict with alternative batch suggestions
        """
        workflow_state = payload.get('workflow_state', {})
        
        request = workflow_state.get('request', {})
        phases = workflow_state.get('phases', {})
        
        # Get current selection and compliance issues
        current_selection = phases.get('batch_selection', {}).get('selected_batches', [])
        compliance = phases.get('compliance', {})
        
        alternatives = []
        
        # For each non-compliant batch, find alternatives
        non_compliant = compliance.get('non_compliant_batches', [])
        
        for batch in non_compliant:
            item_code = batch.get('item_code')
            parsed = parse_golden_number(item_code)
            
            if parsed:
                # Get all available batches for this product
                available = get_available_batches(
                    product_code=parsed['product'],
                    warehouse=batch.get('warehouse', 'FG to Sell Warehouse - AMB-W')
                )
                
                # Filter out already selected and non-compliant batches
                current_batch_names = [b.get('batch_name') for b in current_selection]
                
                for alt_batch in available:
                    if alt_batch['batch_name'] in current_batch_names:
                        continue
                    
                    # Check if this batch is compliant
                    tds_requirements = request.get('tds_requirements', {})
                    coa_params = get_batch_coa_parameters(alt_batch['batch_name'])
                    
                    if coa_params:
                        alt_compliance = check_tds_compliance(coa_params, tds_requirements)
                        
                        if alt_compliance['all_pass']:
                            alternatives.append({
                                "replaces": batch.get('batch_name'),
                                "alternative": alt_batch,
                                "compliance": alt_compliance['parameters']
                            })
        
        return {
            "alternatives": alternatives,
            "total_found": len(alternatives),
            "message": f"Found {len(alternatives)} compliant alternatives"
        }
    
    def _optimize_blend(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Optimize blend ratios to meet target specifications.
        
        Args (in payload):
            available_batches: List of available batches with COA data
            target_spec: Target specification {param: {target, tolerance}}
            total_qty: Total quantity needed
            
        Returns:
            Dict with optimized blend ratios
        """
        available_batches = payload.get('available_batches', [])
        target_spec = payload.get('target_spec', {})
        total_qty = payload.get('total_qty', 1000)
        
        if not available_batches:
            return {"error": "No batches available for blending"}
        
        # Simple optimization: find batches that bracket the target
        # More sophisticated optimization would use linear programming
        
        blend_ratios = []
        
        for param_name, spec in target_spec.items():
            target_value = spec.get('target')
            if not target_value:
                continue
            
            # Find batches above and below target
            above = []
            below = []
            
            for batch in available_batches:
                batch_name = batch.get('batch_name')
                coa_params = get_batch_coa_parameters(batch_name)
                
                if coa_params and param_name in coa_params:
                    value = coa_params[param_name].get('value')
                    if value is not None:
                        if value >= target_value:
                            above.append((batch, value))
                        else:
                            below.append((batch, value))
            
            # If we have batches on both sides, we can blend to target
            if above and below:
                # Simple 2-batch blend
                batch_high, value_high = above[0]
                batch_low, value_low = below[0]
                
                # Calculate ratios: (target - low) / (high - low) = ratio_high
                if value_high != value_low:
                    ratio_high = (target_value - value_low) / (value_high - value_low)
                    ratio_low = 1 - ratio_high
                    
                    blend_ratios.append({
                        "parameter": param_name,
                        "target": target_value,
                        "blend": [
                            {
                                "batch": batch_high.get('batch_name'),
                                "ratio": ratio_high,
                                "qty": total_qty * ratio_high,
                                "value": value_high
                            },
                            {
                                "batch": batch_low.get('batch_name'),
                                "ratio": ratio_low,
                                "qty": total_qty * ratio_low,
                                "value": value_low
                            }
                        ],
                        "predicted_value": value_high * ratio_high + value_low * ratio_low
                    })
        
        return {
            "blend_optimization": blend_ratios,
            "total_qty": total_qty,
            "feasible": len(blend_ratios) > 0
        }
    
    def _find_compliant_batches(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Find all batches that comply with given TDS requirements.
        
        Args (in payload):
            product_code: Product code to search
            warehouse: Warehouse
            tds_requirements: TDS spec
            
        Returns:
            List of compliant batches
        """
        product_code = payload.get('product_code')
        warehouse = payload.get('warehouse', 'FG to Sell Warehouse - AMB-W')
        tds_requirements = payload.get('tds_requirements', {})
        
        # Get all available batches
        available = get_available_batches(product_code, warehouse)
        
        compliant = []
        
        for batch in available:
            batch_name = batch.get('batch_name')
            if not batch_name:
                continue
            
            coa_params = get_batch_coa_parameters(batch_name)
            if not coa_params:
                continue
            
            compliance = check_tds_compliance(coa_params, tds_requirements)
            
            if compliance['all_pass']:
                compliant.append({
                    **batch,
                    "compliance": compliance['parameters']
                })
        
        return {
            "compliant_batches": compliant,
            "total_found": len(compliant),
            "total_searched": len(available)
        }
    
    def _find_alternatives_for_batch(
        self,
        batch: Dict,
        tds_requirements: Dict,
        constraints: Dict
    ) -> List[Dict]:
        """Find alternative batches that comply with TDS."""
        item_code = batch.get('item_code')
        parsed = parse_golden_number(item_code)
        
        if not parsed:
            return []
        
        available = get_available_batches(
            product_code=parsed['product'],
            warehouse=batch.get('warehouse', 'FG to Sell Warehouse - AMB-W')
        )
        
        alternatives = []
        max_alternatives = constraints.get('max_alternatives', 3)
        
        for alt_batch in available:
            if alt_batch.get('batch_name') == batch.get('batch_name'):
                continue
            
            batch_name = alt_batch.get('batch_name')
            coa_params = get_batch_coa_parameters(batch_name)
            
            if coa_params:
                compliance = check_tds_compliance(coa_params, tds_requirements)
                
                if compliance['all_pass']:
                    alternatives.append({
                        "batch_name": batch_name,
                        "item_code": alt_batch.get('item_code'),
                        "qty_available": alt_batch.get('qty'),
                        "fefo_key": alt_batch.get('fefo_key'),
                        "compliance": compliance['parameters']
                    })
                    
                    if len(alternatives) >= max_alternatives:
                        break
        
        return alternatives
    
    def _optimize_for_cost(
        self,
        current_selection: List[Dict],
        constraints: Dict
    ) -> Optional[Dict]:
        """Optimize selection for minimum cost."""
        # Placeholder for cost optimization logic
        # Would need actual cost data from ERPNext
        return None


# Export for auto-discovery
AGENT_CLASS = OptimizationEngine
