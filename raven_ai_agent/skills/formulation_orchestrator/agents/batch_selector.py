"""
Batch Selector Agent - Phase 2
==============================

Intelligent batch selection based on FEFO, TDS compliance, and cost optimization.
Uses formulation_reader functions for data access.
"""

import frappe
from typing import Dict, List, Any, Optional
from datetime import datetime

from .base import BaseSubAgent
from ..messages import AgentMessage, WorkflowPhase, AgentChannel

# Import formulation_reader functions
from ...formulation_reader.reader import (
    parse_golden_number,
    get_available_batches,
    get_batch_coa_parameters,
    check_tds_compliance
)


class BatchSelectorAgent(BaseSubAgent):
    """
    Batch Selector Agent (Phase 2 of workflow).
    
    Responsibilities:
    - Query available batches from Bin doctype
    - Apply FEFO sorting (First Expired, First Out)
    - Filter by TDS compliance
    - Return optimal batch selection
    
    Uses formulation_reader for all data access.
    """
    
    name = "batch_selector"
    description = "Intelligent batch selection with FEFO and TDS compliance"
    emoji = "📦"
    phase = WorkflowPhase.BATCH_SELECTION
    
    def __init__(self, channel: AgentChannel = None):
        super().__init__(channel)
        self._selection_cache: Dict[str, List] = {}
    
    def process(self, action: str, payload: Dict, message: AgentMessage) -> Optional[Dict]:
        """Route to specific action handler."""
        actions = {
            "select_batches": self._select_batches,
            "get_fefo_sorted": self._get_fefo_sorted,
            "filter_by_tds": self._filter_by_tds,
            "select_optimal": self._select_optimal,
        }
        
        handler = actions.get(action)
        if handler:
            return handler(payload, message)
        return None
    
    def _select_batches(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Main batch selection action.
        
        Args (in payload):
            item_code: Item code to select batches for
            warehouse: Warehouse to query (default: 'FG to Sell Warehouse - AMB-W')
            quantity_required: Required quantity
            production_date: Target production date
            tds_spec: Optional TDS specification for filtering
            
        Returns:
            Dict with selected_batches, total_qty, coverage_percent
        """
        item_code = payload.get('item_code')
        warehouse = payload.get('warehouse', 'FG to Sell Warehouse - AMB-W')
        quantity_required = payload.get('quantity_required', 0)
        tds_spec = payload.get('tds_spec')
        
        self._log(f"Selecting batches for {item_code} in {warehouse}")
        self.send_status("selecting", {"item_code": item_code})
        
        # Parse item code to get product code
        parsed = parse_golden_number(item_code)
        product_code = parsed['product'] if parsed else None
        
        # Get all available batches sorted by FEFO
        available = get_available_batches(
            product_code=product_code,
            warehouse=warehouse
        )
        
        if not available:
            return {
                "selected_batches": [],
                "total_qty": 0,
                "coverage_percent": 0,
                "message": f"No available batches found for product {product_code}"
            }
        
        # Filter by TDS if spec provided
        if tds_spec:
            available = self._apply_tds_filter(available, tds_spec)
        
        # Select batches to meet quantity requirement
        selected = []
        total_qty = 0
        
        for batch in available:
            if quantity_required and total_qty >= quantity_required:
                break
            
            selected.append({
                "batch_name": batch['batch_name'],
                "item_code": batch['item_code'],
                "warehouse": batch['warehouse'],
                "qty_available": batch['qty'],
                "fefo_key": batch['fefo_key'],
                "year": batch['year'],
                "folio": batch['folio'],
            })
            total_qty += batch['qty']
        
        coverage = (total_qty / quantity_required * 100) if quantity_required else 100
        
        self.send_status("completed", {
            "batches_selected": len(selected),
            "total_qty": total_qty,
            "coverage": coverage
        })
        
        return {
            "selected_batches": selected,
            "total_qty": total_qty,
            "coverage_percent": min(coverage, 100),
            "message": f"Selected {len(selected)} batches with {total_qty} units ({coverage:.1f}% coverage)"
        }
    
    def _get_fefo_sorted(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Get FEFO-sorted batches without quantity filtering.
        
        Args (in payload):
            product_code: 4-digit product code
            warehouse: Warehouse to query
            
        Returns:
            Dict with batches list sorted by FEFO key
        """
        product_code = payload.get('product_code')
        warehouse = payload.get('warehouse', 'FG to Sell Warehouse - AMB-W')
        
        batches = get_available_batches(
            product_code=product_code,
            warehouse=warehouse
        )
        
        return {
            "batches": batches,
            "count": len(batches),
            "sort_order": "FEFO (oldest first)"
        }
    
    def _filter_by_tds(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Filter batches by TDS compliance.
        
        Args (in payload):
            batches: List of batch records
            tds_spec: TDS specification {param_name: {min, max}}
            
        Returns:
            Dict with compliant and non_compliant batches
        """
        batches = payload.get('batches', [])
        tds_spec = payload.get('tds_spec', {})
        
        compliant = []
        non_compliant = []
        
        for batch in batches:
            batch_name = batch.get('batch_name')
            if not batch_name:
                non_compliant.append({**batch, "reason": "No batch name"})
                continue
            
            # Get COA parameters
            coa_params = get_batch_coa_parameters(batch_name)
            if not coa_params:
                non_compliant.append({**batch, "reason": "No COA found"})
                continue
            
            # Check TDS compliance
            compliance = check_tds_compliance(coa_params, tds_spec)
            
            if compliance['all_pass']:
                compliant.append({
                    **batch,
                    "compliance": compliance['parameters']
                })
            else:
                non_compliant.append({
                    **batch,
                    "reason": "TDS non-compliance",
                    "compliance": compliance['parameters']
                })
        
        return {
            "compliant": compliant,
            "non_compliant": non_compliant,
            "summary": {
                "total": len(batches),
                "compliant_count": len(compliant),
                "non_compliant_count": len(non_compliant)
            }
        }
    
    def _select_optimal(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Select optimal batches considering FEFO, TDS, and cost.
        
        Args (in payload):
            item_code: Item code
            quantity_required: Required quantity
            warehouse: Warehouse
            tds_spec: TDS specification
            cost_priority: Weight for cost optimization (0-1)
            
        Returns:
            Dict with optimal selection and rationale
        """
        item_code = payload.get('item_code')
        quantity_required = payload.get('quantity_required', 0)
        warehouse = payload.get('warehouse', 'FG to Sell Warehouse - AMB-W')
        tds_spec = payload.get('tds_spec')
        cost_priority = payload.get('cost_priority', 0.3)
        
        # Get FEFO-sorted batches
        parsed = parse_golden_number(item_code)
        product_code = parsed['product'] if parsed else None
        
        available = get_available_batches(product_code, warehouse)
        
        if not available:
            return {"error": "No batches available", "selected": []}
        
        # Score each batch
        scored_batches = []
        for batch in available:
            score = self._calculate_batch_score(batch, tds_spec, cost_priority)
            scored_batches.append({**batch, "score": score})
        
        # Sort by score (higher is better)
        scored_batches.sort(key=lambda x: x['score'], reverse=True)
        
        # Select to meet quantity
        selected = []
        total_qty = 0
        
        for batch in scored_batches:
            if total_qty >= quantity_required:
                break
            selected.append(batch)
            total_qty += batch['qty']
        
        return {
            "selected": selected,
            "total_qty": total_qty,
            "coverage_percent": min(total_qty / quantity_required * 100, 100) if quantity_required else 100,
            "rationale": f"Selected {len(selected)} batches based on FEFO + TDS compliance + cost optimization"
        }
    
    def _apply_tds_filter(self, batches: List[Dict], tds_spec: Dict) -> List[Dict]:
        """Filter batches by TDS compliance."""
        compliant = []
        
        for batch in batches:
            batch_name = batch.get('batch_name')
            if not batch_name:
                continue
            
            coa_params = get_batch_coa_parameters(batch_name)
            if not coa_params:
                continue
            
            compliance = check_tds_compliance(coa_params, tds_spec)
            if compliance['all_pass']:
                compliant.append(batch)
        
        return compliant
    
    def _calculate_batch_score(
        self, 
        batch: Dict, 
        tds_spec: Dict = None,
        cost_priority: float = 0.3
    ) -> float:
        """
        Calculate optimization score for a batch.
        
        Score components:
        - FEFO score (higher for older batches)
        - TDS compliance score (1.0 if compliant, 0 if not)
        - Cost score (placeholder - would need pricing data)
        """
        score = 0.0
        
        # FEFO score: inverse of fefo_key (older = higher score)
        # Normalize assuming fefo_key range 0-99999
        fefo_key = batch.get('fefo_key', 99999)
        fefo_score = 1.0 - (fefo_key / 99999)
        score += fefo_score * 0.4  # 40% weight for FEFO
        
        # TDS compliance score
        if tds_spec:
            batch_name = batch.get('batch_name')
            if batch_name:
                coa_params = get_batch_coa_parameters(batch_name)
                if coa_params:
                    compliance = check_tds_compliance(coa_params, tds_spec)
                    tds_score = 1.0 if compliance['all_pass'] else 0.0
                    score += tds_score * 0.4  # 40% weight for TDS
        else:
            score += 0.4  # No TDS spec = assume compliant
        
        # Cost score (placeholder - 20% weight)
        # Would need actual cost data from ERPNext
        cost_score = 0.5  # Neutral score without real data
        score += cost_score * 0.2 * cost_priority
        
        return score


# Export for auto-discovery
AGENT_CLASS = BatchSelectorAgent
