"""
Cost Calculator Agent - Phase 4
===============================

Calculates costs for batch selections and formulations.
"""

import frappe
from typing import Dict, List, Any, Optional, Tuple
from decimal import Decimal
from datetime import date

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
            "calculate_formulation_cost": self._calculate_formulation_cost,  # Phase 3 integration
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
    
    def _transform_phase3_input(self, phase3_output: Dict) -> Tuple[List[Dict], Dict, List[Dict]]:
        """
        Transform Phase 3 compliance_results to internal batch list.
        
        Args:
            phase3_output: Output from Phase 3 TDS Compliance Agent
            
        Returns:
            Tuple of (batches_list, formulation_request, warnings)
        """
        batches = []
        warnings = []
        
        compliance_results = phase3_output.get('compliance_results', [])
        formulation_request = phase3_output.get('formulation_request', {})
        
        for item_result in compliance_results:
            item_code = item_result.get('item_code')
            item_status = item_result.get('item_compliance_status')
            
            # Check item-level compliance
            if item_status != 'ALL_COMPLIANT':
                warnings.append({
                    'item_code': item_code,
                    'warning': 'PARTIAL_COMPLIANCE',
                    'message': f'Item {item_code} is not fully compliant: {item_status}',
                    'action_required': 'Review non-compliant batches'
                })
            
            for batch in item_result.get('batches_checked', []):
                tds_status = batch.get('tds_status')
                
                # Only process COMPLIANT batches
                if tds_status != 'COMPLIANT':
                    warnings.append({
                        'batch_id': batch.get('batch_id'),
                        'warning': 'NON_COMPLIANT_BATCH',
                        'message': f'Skipping batch {batch.get("batch_no")}: {tds_status}',
                        'action_required': 'Use compliant batches only'
                    })
                    continue
                
                batches.append({
                    'batch_name': batch.get('batch_no') or batch.get('batch_id'),
                    'batch_id': batch.get('batch_id'),
                    'item_code': item_code,
                    'qty': batch.get('allocated_qty', 0),
                    'warehouse': batch.get('warehouse')
                })
        
        return batches, formulation_request, warnings
    
    def _get_item_price(self, item_code: str, price_list: str = 'Standard Buying', 
                        batch_no: str = None, qty: float = 1) -> Optional[Dict]:
        """
        Get the best available price for an item following specification priority.
        
        Priority Order:
        1. Batch-specific Item Price
        2. Item Price with valid dates for specified price_list
        3. Item Price for specified price_list (any date)
        4. Item.standard_rate
        5. Item.last_purchase_rate
        6. Item.valuation_rate
        
        Args:
            item_code: Item code to price
            price_list: Preferred price list (default: Standard Buying)
            batch_no: Batch for batch-specific pricing
            qty: Quantity for quantity-based pricing
        
        Returns:
            Dict with price, currency, source, price_list, valid_from
            Returns None if no price found
        """
        today = date.today()
        default_currency = frappe.defaults.get_global_default('currency') or 'MXN'
        
        # 1. Try batch-specific price
        if batch_no:
            batch_price = frappe.get_all(
                'Item Price',
                filters={
                    'item_code': item_code,
                    'price_list': price_list,
                    'batch_no': batch_no,
                    'valid_from': ['<=', today]
                },
                or_filters=[
                    ['valid_upto', '>=', today],
                    ['valid_upto', 'is', 'not set']
                ],
                fields=['price_list_rate', 'currency', 'uom', 'valid_from', 'valid_upto'],
                order_by='valid_from desc',
                limit=1
            )
            if batch_price:
                return {
                    'price': float(batch_price[0].price_list_rate),
                    'currency': batch_price[0].currency,
                    'uom': batch_price[0].uom,
                    'source': 'Item Price (Batch)',
                    'price_list': price_list,
                    'valid_from': str(batch_price[0].valid_from) if batch_price[0].valid_from else None,
                    'valid_upto': str(batch_price[0].valid_upto) if batch_price[0].valid_upto else None
                }
        
        # 2. Try Item Price with valid dates
        item_price = frappe.get_all(
            'Item Price',
            filters={
                'item_code': item_code,
                'price_list': price_list,
                'valid_from': ['<=', today]
            },
            or_filters=[
                ['valid_upto', '>=', today],
                ['valid_upto', 'is', 'not set']
            ],
            fields=['price_list_rate', 'currency', 'uom', 'valid_from', 'valid_upto', 'min_qty'],
            order_by='valid_from desc',
            limit=5
        )
        
        # Filter by min_qty
        for price in item_price:
            min_qty = price.get('min_qty') or 0
            if qty >= min_qty:
                return {
                    'price': float(price.price_list_rate),
                    'currency': price.currency,
                    'uom': price.uom,
                    'source': 'Item Price',
                    'price_list': price_list,
                    'valid_from': str(price.valid_from) if price.valid_from else None,
                    'valid_upto': str(price.valid_upto) if price.valid_upto else None
                }
        
        # 3. Try any Item Price for this price_list (no date filter)
        any_price = frappe.get_all(
            'Item Price',
            filters={
                'item_code': item_code,
                'price_list': price_list
            },
            fields=['price_list_rate', 'currency', 'uom', 'valid_from'],
            order_by='valid_from desc',
            limit=1
        )
        if any_price:
            return {
                'price': float(any_price[0].price_list_rate),
                'currency': any_price[0].currency,
                'uom': any_price[0].uom,
                'source': 'Item Price (No Date Filter)',
                'price_list': price_list,
                'valid_from': str(any_price[0].valid_from) if any_price[0].valid_from else None,
                'valid_upto': None
            }
        
        # 4-6. Fallback to Item document rates
        try:
            item = frappe.get_doc('Item', item_code)
            stock_uom = item.stock_uom
            
            # 4. standard_rate
            if item.standard_rate:
                return {
                    'price': float(item.standard_rate),
                    'currency': default_currency,
                    'uom': stock_uom,
                    'source': 'Item Standard Rate',
                    'price_list': None,
                    'valid_from': None,
                    'valid_upto': None
                }
            
            # 5. last_purchase_rate
            if item.last_purchase_rate:
                return {
                    'price': float(item.last_purchase_rate),
                    'currency': default_currency,
                    'uom': stock_uom,
                    'source': 'Last Purchase Rate',
                    'price_list': None,
                    'valid_from': None,
                    'valid_upto': None
                }
            
            # 6. valuation_rate
            if item.valuation_rate:
                return {
                    'price': float(item.valuation_rate),
                    'currency': default_currency,
                    'uom': stock_uom,
                    'source': 'Valuation Rate',
                    'price_list': None,
                    'valid_from': None,
                    'valid_upto': None
                }
        except Exception as e:
            self._log(f"Error getting Item rates for {item_code}: {e}", level="warning")
        
        # No price found
        return None
    
    def _calculate_formulation_cost(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Calculate costs using Phase 3 compliance_results format.
        Returns output matching the contract specification.
        
        Args (in payload):
            compliance_results: List from Phase 3
            formulation_request: Target formulation details
            price_list: Price list to use (default: Standard Buying)
        
        Returns:
            Dict matching Phase 4 output contract
        """
        price_list = payload.get('price_list', 'Standard Buying')
        
        # Transform Phase 3 input
        batches, formulation_request, warnings = self._transform_phase3_input(payload)
        
        self._log(f"Calculating costs for {len(batches)} compliant batches")
        self.send_status("calculating", {"batch_count": len(batches)})
        
        # Group by item_code
        items_map = {}
        pricing_sources = []
        
        for batch in batches:
            item_code = batch['item_code']
            if item_code not in items_map:
                # Get item name
                try:
                    item_doc = frappe.get_doc('Item', item_code)
                    item_name = item_doc.item_name
                    uom = item_doc.stock_uom
                except:
                    item_name = item_code
                    uom = 'Kg'
                
                items_map[item_code] = {
                    'item_code': item_code,
                    'item_name': item_name,
                    'total_qty': 0,
                    'uom': uom,
                    'batch_costs': [],
                    'item_total_cost': Decimal('0')
                }
            
            # Get price for this batch
            batch_no = batch['batch_name']
            qty = Decimal(str(batch['qty']))
            
            price_info = self._get_item_price(item_code, price_list, batch_no, float(qty))
            
            if not price_info:
                warnings.append({
                    'item_code': item_code,
                    'batch_no': batch_no,
                    'error': 'NO_PRICE',
                    'message': f'No price found for {item_code} batch {batch_no}',
                    'action_required': 'Define Item Price or set rates on Item'
                })
                price_info = {
                    'price': 0,
                    'currency': 'MXN',
                    'uom': items_map[item_code]['uom'],
                    'source': 'Not Found',
                    'price_list': None,
                    'valid_from': None
                }
            
            unit_price = Decimal(str(price_info['price']))
            batch_cost = qty * unit_price
            
            items_map[item_code]['batch_costs'].append({
                'batch_id': batch.get('batch_id'),
                'batch_no': batch_no,
                'allocated_qty': float(qty),
                'unit_price': float(unit_price),
                'price_currency': price_info['currency'],
                'price_list': price_info.get('price_list'),
                'batch_cost': float(batch_cost.quantize(Decimal('0.01')))
            })
            
            items_map[item_code]['total_qty'] += float(qty)
            items_map[item_code]['item_total_cost'] += batch_cost
            
            # Record pricing source (first occurrence per item)
            if not any(ps['item_code'] == item_code for ps in pricing_sources):
                pricing_sources.append({
                    'item_code': item_code,
                    'source': price_info['source'],
                    'price_list': price_info.get('price_list'),
                    'valid_from': price_info.get('valid_from')
                })
        
        # Build cost_breakdown array
        cost_breakdown = []
        total_material_cost = Decimal('0')
        
        for item_code, item_data in items_map.items():
            item_data['item_total_cost'] = float(item_data['item_total_cost'].quantize(Decimal('0.01')))
            total_material_cost += Decimal(str(item_data['item_total_cost']))
            cost_breakdown.append(item_data)
        
        # Calculate summary
        finished_qty = float(formulation_request.get('target_quantity_kg', 1))
        finished_uom = formulation_request.get('uom', 'Kg')
        
        # Get currency from first batch or default
        currency = 'MXN'
        if cost_breakdown and cost_breakdown[0]['batch_costs']:
            currency = cost_breakdown[0]['batch_costs'][0].get('price_currency', 'MXN')
        
        total_cost = float(total_material_cost.quantize(Decimal('0.01')))
        cost_per_unit = total_cost / finished_qty if finished_qty > 0 else 0
        
        self.send_status("completed", {
            "total_cost": total_cost,
            "items_costed": len(cost_breakdown),
            "currency": currency
        })
        
        return {
            'cost_breakdown': cost_breakdown,
            'summary': {
                'total_material_cost': total_cost,
                'currency': currency,
                'finished_qty': finished_qty,
                'finished_uom': finished_uom,
                'cost_per_unit': round(cost_per_unit, 2),
                'items_costed': len(cost_breakdown),
                'batches_costed': sum(len(item['batch_costs']) for item in cost_breakdown)
            },
            'pricing_sources': pricing_sources,
            'warnings': warnings
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
