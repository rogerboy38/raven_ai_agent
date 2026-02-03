"""
Cost Calculator Agent - Phase 4
===============================

Calculates costs for batch selections and formulations.
"""

import frappe
from typing import Dict, List, Any, Optional
from decimal import Decimal

from .base import BaseSubAgent
from ..messages import AgentMessage, WorkflowPhase, AgentChannel


class CostCalculatorAgent(BaseSubAgent):
    """
    Cost Calculator Agent (Phase 4 of workflow).
    
    Responsibilities:
    - Calculate raw material costs
    - Estimate production costs
    - Compare cost scenarios
    - Provide cost optimization suggestions
    """
    
    name = "cost_calculator"
    description = "Cost calculation and optimization"
    emoji = "💰"
    phase = WorkflowPhase.COST_CALCULATION
    
    def process(self, action: str, payload: Dict, message: AgentMessage) -> Optional[Dict]:
        """Route to specific action handler."""
        actions = {
            "calculate_costs": self._calculate_costs,
            "estimate_batch_cost": self._estimate_batch_cost,
            "compare_scenarios": self._compare_scenarios,
            "get_cost_breakdown": self._get_cost_breakdown,
        }
        
        handler = actions.get(action)
        if handler:
            return handler(payload, message)
        return None
    
    def _calculate_costs(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Calculate total costs for a batch selection.
        
        Args (in payload):
            batches: List of selected batches [{batch_name, qty, item_code, ...}]
            include_overhead: Whether to include overhead costs
            currency: Currency code (default: MXN)
            
        Returns:
            Dict with total_cost, cost_breakdown, cost_per_unit
        """
        batches = payload.get('batches', [])
        include_overhead = payload.get('include_overhead', True)
        currency = payload.get('currency', 'MXN')
        
        self._log(f"Calculating costs for {len(batches)} batches")
        self.send_status("calculating", {"batch_count": len(batches)})
        
        total_raw_material = Decimal('0')
        total_qty = Decimal('0')
        batch_costs = []
        
        for batch in batches:
            batch_name = batch.get('batch_name')
            item_code = batch.get('item_code')
            qty = Decimal(str(batch.get('qty', 0)))
            
            # Get item valuation rate
            unit_cost = self._get_item_valuation_rate(item_code)
            batch_cost = unit_cost * qty
            
            batch_costs.append({
                "batch_name": batch_name,
                "item_code": item_code,
                "qty": float(qty),
                "unit_cost": float(unit_cost),
                "total_cost": float(batch_cost)
            })
            
            total_raw_material += batch_cost
            total_qty += qty
        
        # Calculate overhead (placeholder - would need actual overhead rates)
        overhead_rate = Decimal('0.15')  # 15% overhead
        overhead = total_raw_material * overhead_rate if include_overhead else Decimal('0')
        
        total_cost = total_raw_material + overhead
        cost_per_unit = total_cost / total_qty if total_qty > 0 else Decimal('0')
        
        self.send_status("completed", {
            "total_cost": float(total_cost),
            "currency": currency
        })
        
        return {
            "total_cost": float(total_cost),
            "raw_material_cost": float(total_raw_material),
            "overhead_cost": float(overhead),
            "total_qty": float(total_qty),
            "cost_per_unit": float(cost_per_unit),
            "currency": currency,
            "batch_costs": batch_costs,
            "overhead_rate": float(overhead_rate) if include_overhead else 0
        }
    
    def _estimate_batch_cost(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Estimate cost for a single batch.
        
        Args (in payload):
            batch_name: Batch name
            item_code: Item code
            qty: Quantity
            
        Returns:
            Dict with estimated cost details
        """
        item_code = payload.get('item_code')
        qty = Decimal(str(payload.get('qty', 0)))
        
        unit_cost = self._get_item_valuation_rate(item_code)
        total_cost = unit_cost * qty
        
        return {
            "item_code": item_code,
            "qty": float(qty),
            "unit_cost": float(unit_cost),
            "total_cost": float(total_cost),
            "valuation_method": "moving_average"
        }
    
    def _compare_scenarios(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Compare costs between different batch selection scenarios.
        
        Args (in payload):
            scenarios: List of scenarios, each with batches list
            
        Returns:
            Dict with scenario comparison and recommendation
        """
        scenarios = payload.get('scenarios', [])
        
        results = []
        
        for i, scenario in enumerate(scenarios):
            scenario_name = scenario.get('name', f'Scenario {i+1}')
            batches = scenario.get('batches', [])
            
            # Calculate cost for this scenario
            cost_result = self._calculate_costs(
                {'batches': batches, 'include_overhead': True},
                message
            )
            
            results.append({
                "scenario_name": scenario_name,
                "total_cost": cost_result['total_cost'],
                "total_qty": cost_result['total_qty'],
                "cost_per_unit": cost_result['cost_per_unit'],
                "batch_count": len(batches)
            })
        
        # Sort by cost per unit to find best option
        results.sort(key=lambda x: x['cost_per_unit'])
        
        return {
            "scenarios": results,
            "recommended": results[0] if results else None,
            "savings_potential": results[-1]['total_cost'] - results[0]['total_cost'] if len(results) > 1 else 0
        }
    
    def _get_cost_breakdown(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Get detailed cost breakdown by category.
        
        Args (in payload):
            batches: List of batches
            categories: List of cost categories to include
            
        Returns:
            Dict with categorized cost breakdown
        """
        batches = payload.get('batches', [])
        
        # Calculate base costs
        base_result = self._calculate_costs(
            {'batches': batches, 'include_overhead': False},
            message
        )
        
        raw_material = Decimal(str(base_result['raw_material_cost']))
        
        # Breakdown by cost category
        breakdown = {
            "raw_materials": float(raw_material),
            "labor": float(raw_material * Decimal('0.05')),  # 5% labor
            "utilities": float(raw_material * Decimal('0.03')),  # 3% utilities
            "packaging": float(raw_material * Decimal('0.02')),  # 2% packaging
            "quality_control": float(raw_material * Decimal('0.02')),  # 2% QC
            "overhead": float(raw_material * Decimal('0.03')),  # 3% overhead
        }
        
        breakdown['total'] = sum(breakdown.values())
        
        # Calculate percentages
        breakdown['percentages'] = {
            k: v / breakdown['total'] * 100 if breakdown['total'] > 0 else 0
            for k, v in breakdown.items() if k != 'total' and k != 'percentages'
        }
        
        return {
            "breakdown": breakdown,
            "total_qty": base_result['total_qty'],
            "cost_per_unit": breakdown['total'] / base_result['total_qty'] if base_result['total_qty'] > 0 else 0
        }
    
    def _get_item_valuation_rate(self, item_code: str) -> Decimal:
        """
        Get the valuation rate for an item.
        
        Uses ERPNext's valuation rate or falls back to standard buying price.
        """
        if not item_code:
            return Decimal('0')
        
        try:
            # Try to get from Bin (weighted average)
            bin_rate = frappe.db.get_value(
                'Bin',
                {'item_code': item_code},
                'valuation_rate'
            )
            
            if bin_rate:
                return Decimal(str(bin_rate))
            
            # Fall back to Item standard rate
            item_rate = frappe.db.get_value(
                'Item',
                item_code,
                'valuation_rate'
            )
            
            if item_rate:
                return Decimal(str(item_rate))
            
            # Last resort: standard buying price
            buying_price = frappe.db.get_value(
                'Item Price',
                {
                    'item_code': item_code,
                    'buying': 1
                },
                'price_list_rate'
            )
            
            return Decimal(str(buying_price or 0))
            
        except Exception as e:
            self._log(f"Error getting valuation rate for {item_code}: {e}", level="warning")
            return Decimal('0')


# Export for auto-discovery
AGENT_CLASS = CostCalculatorAgent
