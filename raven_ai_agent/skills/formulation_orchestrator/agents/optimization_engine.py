"""
Optimization Engine Agent - Phase 5
====================================

Optimizes batch selections using multiple strategies.
Provides what-if analysis and constraint validation.
"""

import frappe
from typing import Dict, List, Any, Optional, Tuple
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from .base import BaseSubAgent
from ..messages import AgentMessage, WorkflowPhase, AgentChannel

from ...formulation_reader.reader import (
    get_available_batches,
    get_batch_coa_parameters,
    check_tds_compliance,
    parse_golden_number
)


class OptimizationStrategy(Enum):
    """Supported optimization strategies."""
    FEFO_COST_BALANCED = "fefo_cost_balanced"
    MINIMIZE_COST = "minimize_cost"
    STRICT_FEFO = "strict_fefo"
    MINIMUM_BATCHES = "minimum_batches"


class OptimizationError(Exception):
    """Base exception for optimization errors."""
    pass


class InsufficientStockError(OptimizationError):
    """Raised when available stock cannot meet requirement."""
    def __init__(self, required, available, item_code=None):
        self.required = required
        self.available = available
        self.shortage = required - available
        self.item_code = item_code
        super().__init__(f"Insufficient stock: need {required}, have {available}")


class NoValidBatchesError(OptimizationError):
    """Raised when no batches meet constraints."""
    def __init__(self, item_code=None, constraint_failures=None):
        self.item_code = item_code
        self.constraint_failures = constraint_failures or []
        super().__init__(f"No valid batches for {item_code}")


class OptimizationEngine(BaseSubAgent):
    """
    Optimization Engine (Phase 5 of workflow).
    
    Responsibilities:
    - Optimize batch selections using multiple strategies
    - Generate what-if scenario comparisons
    - Validate constraint satisfaction
    - Integrate with Phase 4 cost data
    """
    
    name = "optimization_engine"
    description = "Batch selection optimization and what-if analysis"
    emoji = "⚡"
    phase = WorkflowPhase.OPTIMIZATION
    
    # Default strategy weights
    DEFAULT_WEIGHTS = {'fefo': 0.6, 'cost': 0.4}
    
    def process(self, action: str, payload: Dict, message: AgentMessage) -> Optional[Dict]:
        """Route to specific action handler."""
        actions = {
            "optimize_selection": self._optimize_selection,
            "generate_what_if": self._generate_what_if_action,
            "validate_constraints": self._validate_constraints_action,
            "compare_strategies": self._compare_strategies,
            # Legacy actions
            "optimize": self._optimize_legacy,
            "suggest_alternatives": self._suggest_alternatives,
            "optimize_blend": self._optimize_blend,
            "find_compliant_batches": self._find_compliant_batches,
        }
        
        handler = actions.get(action)
        if handler:
            return handler(payload, message)
        return None
    
    # =========================================================================
    # NEW PHASE 5 ACTIONS
    # =========================================================================
    
    def _optimize_selection(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Main optimization entry point for Phase 4 integration.
        
        Args (in payload):
            available_batches: List of batches with cost and expiry data
            required_qty: Quantity needed
            strategy: Optimization strategy (default: fefo_cost_balanced)
            constraints: Optional constraints dict
            cost_data: Optional Phase 4 cost analysis output
            
        Returns:
            Dict matching Phase 5 output contract
        """
        available_batches = payload.get('available_batches', [])
        required_qty = float(payload.get('required_qty', 0))
        strategy_name = payload.get('strategy', 'fefo_cost_balanced')
        constraints = payload.get('constraints', {})
        cost_data = payload.get('cost_data', {})
        
        self._log(f"Optimizing selection: {len(available_batches)} batches, need {required_qty}, strategy={strategy_name}")
        self.send_status("optimizing", {
            "batch_count": len(available_batches),
            "required_qty": required_qty,
            "strategy": strategy_name
        })
        
        warnings = []
        
        # Validate inputs
        if not available_batches:
            return {
                'optimization_result': {
                    'status': 'FAILED',
                    'strategy_used': strategy_name,
                    'original_cost': 0,
                    'optimized_cost': 0,
                    'savings_amount': 0,
                    'savings_percent': 0
                },
                'selected_batches': [],
                'summary': self._create_empty_summary(strategy_name),
                'what_if_scenarios': {},
                'comparison': {},
                'warnings': [{'type': 'NO_BATCHES', 'message': 'No batches available'}]
            }
        
        # Apply constraints filter
        filtered_batches, filter_warnings = self._apply_constraint_filters(
            available_batches, constraints
        )
        warnings.extend(filter_warnings)
        
        if not filtered_batches:
            return {
                'optimization_result': {
                    'status': 'FAILED',
                    'strategy_used': strategy_name,
                    'original_cost': 0,
                    'optimized_cost': 0,
                    'savings_amount': 0,
                    'savings_percent': 0
                },
                'selected_batches': [],
                'summary': self._create_empty_summary(strategy_name),
                'what_if_scenarios': {},
                'comparison': {},
                'warnings': warnings + [{'type': 'NO_VALID_BATCHES', 'message': 'No batches meet constraints'}]
            }
        
        # Get weights from cost_data if available (cost trend adjustment)
        weights = self._get_adjusted_weights(cost_data)
        
        # Execute optimization strategy
        try:
            strategy = OptimizationStrategy(strategy_name)
        except ValueError:
            strategy = OptimizationStrategy.FEFO_COST_BALANCED
            warnings.append({
                'type': 'INVALID_STRATEGY',
                'message': f"Unknown strategy '{strategy_name}', using default"
            })
        
        selected_batches, selection_warnings = self._execute_strategy(
            filtered_batches, required_qty, strategy, weights, constraints
        )
        warnings.extend(selection_warnings)
        
        # Calculate totals and metrics
        total_qty = sum(b.get('allocated_qty', 0) for b in selected_batches)
        total_cost = sum(b.get('total_cost', 0) for b in selected_batches)
        
        # Check fulfillment
        status = 'OPTIMIZED'
        if total_qty < required_qty:
            status = 'PARTIAL'
            warnings.append({
                'type': 'INSUFFICIENT_STOCK',
                'message': f"Only {total_qty:.2f} available, need {required_qty:.2f}",
                'shortage': required_qty - total_qty
            })
        
        # Count FEFO violations
        fefo_violations = self._count_fefo_violations(selected_batches, available_batches)
        
        # Generate what-if scenarios
        what_if = self._generate_what_if_scenarios(
            filtered_batches, required_qty, constraints, weights
        )
        
        # Calculate original cost (using strict FEFO as baseline)
        original_cost = what_if.get('scenarios', {}).get('strict_fefo', {}).get('total_cost', total_cost)
        savings_amount = original_cost - total_cost
        savings_percent = (savings_amount / original_cost * 100) if original_cost > 0 else 0
        
        # Validate constraints on final selection
        constraint_validation = self._validate_constraints(selected_batches, constraints)
        
        # Build summary
        earliest_expiry = None
        if selected_batches:
            expiry_dates = [b.get('expiry_date') for b in selected_batches if b.get('expiry_date')]
            if expiry_dates:
                earliest_expiry = min(expiry_dates) if isinstance(expiry_dates[0], (date, datetime)) else min(expiry_dates)
        
        summary = {
            'total_quantity': total_qty,
            'total_cost': round(total_cost, 2),
            'average_unit_cost': round(total_cost / total_qty, 2) if total_qty > 0 else 0,
            'batch_count': len(selected_batches),
            'earliest_expiry': str(earliest_expiry) if earliest_expiry else None,
            'fefo_violations': fefo_violations,
            'constraints_satisfied': constraint_validation['valid'],
            'strategy_used': strategy.value
        }
        
        self.send_status("completed", {
            "status": status,
            "batches_selected": len(selected_batches),
            "total_cost": total_cost
        })
        
        return {
            'optimization_result': {
                'status': status,
                'strategy_used': strategy.value,
                'original_cost': round(original_cost, 2),
                'optimized_cost': round(total_cost, 2),
                'savings_amount': round(savings_amount, 2),
                'savings_percent': round(savings_percent, 2)
            },
            'selected_batches': selected_batches,
            'summary': summary,
            'what_if_scenarios': what_if.get('scenarios', {}),
            'comparison': what_if.get('comparison', {}),
            'warnings': warnings
        }
    
    def _generate_what_if_action(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Generate what-if scenarios for comparison.
        
        Args (in payload):
            available_batches: List of batches
            required_qty: Quantity needed
            constraints: Optional constraints
            
        Returns:
            Dict with scenario comparisons
        """
        available_batches = payload.get('available_batches', [])
        required_qty = float(payload.get('required_qty', 0))
        constraints = payload.get('constraints', {})
        
        return self._generate_what_if_scenarios(
            available_batches, required_qty, constraints
        )
    
    def _validate_constraints_action(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Validate a selection against constraints.
        
        Args (in payload):
            selected_batches: List of selected batches
            constraints: Constraints to validate against
            
        Returns:
            Dict with validation results
        """
        selected_batches = payload.get('selected_batches', [])
        constraints = payload.get('constraints', {})
        
        return self._validate_constraints(selected_batches, constraints)
    
    def _compare_strategies(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Compare all optimization strategies.
        
        Args (in payload):
            available_batches: List of batches
            required_qty: Quantity needed
            constraints: Optional constraints
            
        Returns:
            Dict with strategy comparison
        """
        return self._generate_what_if_action(payload, message)
    
    # =========================================================================
    # OPTIMIZATION STRATEGIES
    # =========================================================================
    
    def _execute_strategy(
        self,
        batches: List[Dict],
        required_qty: float,
        strategy: OptimizationStrategy,
        weights: Dict = None,
        constraints: Dict = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """Execute the specified optimization strategy."""
        
        if strategy == OptimizationStrategy.FEFO_COST_BALANCED:
            return self._fefo_cost_balanced(batches, required_qty, weights, constraints)
        elif strategy == OptimizationStrategy.MINIMIZE_COST:
            return self._minimize_cost(batches, required_qty, constraints)
        elif strategy == OptimizationStrategy.STRICT_FEFO:
            return self._strict_fefo(batches, required_qty, constraints)
        elif strategy == OptimizationStrategy.MINIMUM_BATCHES:
            return self._minimum_batches(batches, required_qty, constraints)
        else:
            # Default to balanced
            return self._fefo_cost_balanced(batches, required_qty, weights, constraints)
    
    def _fefo_cost_balanced(
        self,
        batches: List[Dict],
        required_qty: float,
        weights: Dict = None,
        constraints: Dict = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        FEFO Cost Balanced strategy - balances expiry with cost.
        
        Algorithm:
        1. Calculate composite score for each batch
        2. Sort by composite score (higher = better)
        3. Allocate from sorted list
        """
        weights = weights or self.DEFAULT_WEIGHTS
        warnings = []
        
        # Calculate scores
        scored_batches = []
        today = date.today()
        
        # Get min/max for normalization
        costs = [b.get('unit_cost', 0) or 0 for b in batches]
        min_cost = min(costs) if costs else 0
        max_cost = max(costs) if costs else 1
        cost_range = max_cost - min_cost or 1
        
        for batch in batches:
            # FEFO score: days to expiry (lower = better, so invert)
            expiry = batch.get('expiry_date')
            if isinstance(expiry, str):
                try:
                    expiry = datetime.strptime(expiry[:10], '%Y-%m-%d').date()
                except:
                    expiry = today + timedelta(days=365)
            elif expiry is None:
                expiry = today + timedelta(days=365)
            
            days_to_expiry = (expiry - today).days if hasattr(expiry, 'days') or isinstance(expiry, date) else 365
            days_to_expiry = max(days_to_expiry, 1)
            
            # Normalize FEFO: 1/days (closer to expiry = higher score for FEFO priority)
            fefo_score = 1 / days_to_expiry
            
            # Cost score: inverse normalized cost (cheaper = higher score)
            unit_cost = batch.get('unit_cost', 0) or 0
            cost_score = 1 - ((unit_cost - min_cost) / cost_range) if cost_range > 0 else 1
            
            # Composite score
            composite = (weights['fefo'] * fefo_score * 100) + (weights['cost'] * cost_score)
            
            scored_batches.append({
                **batch,
                '_composite_score': composite,
                '_fefo_score': fefo_score,
                '_cost_score': cost_score,
                '_days_to_expiry': days_to_expiry
            })
        
        # Sort by composite score (descending)
        scored_batches.sort(key=lambda b: b['_composite_score'], reverse=True)
        
        # Allocate
        selected = self._allocate_batches(scored_batches, required_qty, 'fefo_cost_balanced')
        
        return selected, warnings
    
    def _minimize_cost(
        self,
        batches: List[Dict],
        required_qty: float,
        constraints: Dict = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Minimize Cost strategy - selects cheapest batches first.
        
        Warning: May result in FEFO violations.
        """
        warnings = [{
            'type': 'STRATEGY_WARNING',
            'message': 'minimize_cost strategy may result in FEFO violations'
        }]
        
        # Sort by unit cost (ascending)
        sorted_batches = sorted(batches, key=lambda b: b.get('unit_cost', 0) or float('inf'))
        
        # Allocate
        selected = self._allocate_batches(sorted_batches, required_qty, 'minimize_cost')
        
        return selected, warnings
    
    def _strict_fefo(
        self,
        batches: List[Dict],
        required_qty: float,
        constraints: Dict = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Strict FEFO strategy - always uses earliest expiring batches first.
        
        Guarantees zero FEFO violations.
        """
        warnings = []
        today = date.today()
        
        def get_expiry_date(batch):
            expiry = batch.get('expiry_date')
            if isinstance(expiry, str):
                try:
                    return datetime.strptime(expiry[:10], '%Y-%m-%d').date()
                except:
                    return date(9999, 12, 31)
            elif isinstance(expiry, date):
                return expiry
            return date(9999, 12, 31)
        
        # Sort by expiry date (ascending)
        sorted_batches = sorted(batches, key=get_expiry_date)
        
        # Allocate
        selected = self._allocate_batches(sorted_batches, required_qty, 'strict_fefo')
        
        return selected, warnings
    
    def _minimum_batches(
        self,
        batches: List[Dict],
        required_qty: float,
        constraints: Dict = None
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Minimum Batches strategy - uses fewest batches possible.
        
        Reduces picking complexity.
        """
        warnings = []
        
        # Sort by available quantity (descending)
        sorted_batches = sorted(
            batches, 
            key=lambda b: b.get('available_qty', 0) or 0, 
            reverse=True
        )
        
        # Allocate
        selected = self._allocate_batches(sorted_batches, required_qty, 'minimum_batches')
        
        return selected, warnings
    
    def _allocate_batches(
        self,
        sorted_batches: List[Dict],
        required_qty: float,
        strategy_name: str
    ) -> List[Dict]:
        """
        Allocate from sorted batch list until quantity is fulfilled.
        
        Returns list of selected batches with allocated quantities.
        """
        selected = []
        remaining = required_qty
        today = date.today()
        
        for batch in sorted_batches:
            if remaining <= 0:
                break
            
            available = batch.get('available_qty', 0) or 0
            if available <= 0:
                continue
            
            # Allocate what we can from this batch
            allocate = min(available, remaining)
            
            # Get expiry info
            expiry = batch.get('expiry_date')
            if isinstance(expiry, str):
                try:
                    expiry_date = datetime.strptime(expiry[:10], '%Y-%m-%d').date()
                    days_to_expiry = (expiry_date - today).days
                except:
                    expiry_date = None
                    days_to_expiry = None
            elif isinstance(expiry, date):
                expiry_date = expiry
                days_to_expiry = (expiry - today).days
            else:
                expiry_date = None
                days_to_expiry = None
            
            unit_cost = batch.get('unit_cost', 0) or 0
            total_cost = allocate * unit_cost
            
            selected.append({
                'batch_id': batch.get('batch_id') or batch.get('name'),
                'batch_no': batch.get('batch_no') or batch.get('batch_name'),
                'item_code': batch.get('item_code'),
                'allocated_qty': allocate,
                'unit_cost': unit_cost,
                'total_cost': round(total_cost, 2),
                'expiry_date': str(expiry_date) if expiry_date else None,
                'days_to_expiry': days_to_expiry,
                'warehouse': batch.get('warehouse'),
                'selection_reason': strategy_name,
                'tds_compliant': batch.get('tds_compliant', True),
                'fefo_rank': batch.get('fefo_rank')
            })
            
            remaining -= allocate
        
        return selected
    
    # =========================================================================
    # CONSTRAINT HANDLING
    # =========================================================================
    
    def _apply_constraint_filters(
        self,
        batches: List[Dict],
        constraints: Dict
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Filter batches based on constraints before optimization.
        
        Returns filtered batches and any warnings generated.
        """
        filtered = batches.copy()
        warnings = []
        today = date.today()
        
        # Min remaining shelf life filter
        min_shelf_life = constraints.get('min_remaining_shelf_life', 0)
        if min_shelf_life > 0:
            original_count = len(filtered)
            filtered = [
                b for b in filtered 
                if self._get_days_to_expiry(b) >= min_shelf_life
            ]
            removed = original_count - len(filtered)
            if removed > 0:
                warnings.append({
                    'type': 'SHELF_LIFE_FILTER',
                    'message': f'Excluded {removed} batches with < {min_shelf_life} days shelf life'
                })
        
        # Warehouse filter
        warehouse_filter = constraints.get('warehouse_filter')
        if warehouse_filter:
            original_count = len(filtered)
            filtered = [
                b for b in filtered 
                if b.get('warehouse') in warehouse_filter
            ]
            removed = original_count - len(filtered)
            if removed > 0:
                warnings.append({
                    'type': 'WAREHOUSE_FILTER',
                    'message': f'Excluded {removed} batches not in allowed warehouses'
                })
        
        # Exclude batches
        exclude_batches = constraints.get('exclude_batches', [])
        if exclude_batches:
            original_count = len(filtered)
            filtered = [
                b for b in filtered 
                if b.get('batch_id') not in exclude_batches and b.get('batch_no') not in exclude_batches
            ]
            removed = original_count - len(filtered)
            if removed > 0:
                warnings.append({
                    'type': 'EXCLUDED_BATCHES',
                    'message': f'Excluded {removed} batches from exclusion list'
                })
        
        # Max cost per unit filter
        max_cost = constraints.get('max_cost_per_unit')
        if max_cost is not None:
            original_count = len(filtered)
            filtered = [
                b for b in filtered 
                if (b.get('unit_cost') or 0) <= max_cost
            ]
            removed = original_count - len(filtered)
            if removed > 0:
                warnings.append({
                    'type': 'COST_FILTER',
                    'message': f'Excluded {removed} batches exceeding max cost {max_cost}'
                })
        
        return filtered, warnings
    
    def _validate_constraints(
        self,
        selection: List[Dict],
        constraints: Dict
    ) -> Dict:
        """
        Validate a selection against constraints.
        
        Returns validation result with any violations.
        """
        violations = []
        
        if not selection:
            return {'valid': True, 'violations': []}
        
        # Max batches constraint
        max_batches = constraints.get('max_batches')
        if max_batches is not None and len(selection) > max_batches:
            violations.append({
                'constraint': 'max_batches',
                'message': f'Selection uses {len(selection)} batches, max is {max_batches}',
                'severity': 'error',
                'affected_batches': [b.get('batch_no') for b in selection[max_batches:]]
            })
        
        # Same warehouse constraint
        if constraints.get('require_same_warehouse'):
            warehouses = set(b.get('warehouse') for b in selection if b.get('warehouse'))
            if len(warehouses) > 1:
                violations.append({
                    'constraint': 'require_same_warehouse',
                    'message': f'Selection spans {len(warehouses)} warehouses',
                    'severity': 'error',
                    'affected_batches': list(warehouses)
                })
        
        # Min shelf life on selected batches
        min_shelf_life = constraints.get('min_remaining_shelf_life', 0)
        if min_shelf_life > 0:
            near_expiry = [
                b for b in selection 
                if (b.get('days_to_expiry') or 0) < min_shelf_life
            ]
            if near_expiry:
                violations.append({
                    'constraint': 'min_remaining_shelf_life',
                    'message': f'{len(near_expiry)} batches have insufficient shelf life',
                    'severity': 'warning',
                    'affected_batches': [b.get('batch_no') for b in near_expiry]
                })
        
        return {
            'valid': len([v for v in violations if v['severity'] == 'error']) == 0,
            'violations': violations
        }
    
    # =========================================================================
    # WHAT-IF SCENARIO GENERATION
    # =========================================================================
    
    def _generate_what_if_scenarios(
        self,
        batches: List[Dict],
        required_qty: float,
        constraints: Dict = None,
        weights: Dict = None
    ) -> Dict:
        """
        Generate what-if scenarios for all strategies.
        
        Returns comparison of all optimization approaches.
        """
        constraints = constraints or {}
        weights = weights or self.DEFAULT_WEIGHTS
        scenarios = {}
        
        # Run each strategy
        for strategy in OptimizationStrategy:
            try:
                selected, _ = self._execute_strategy(
                    batches, required_qty, strategy, weights, constraints
                )
                
                total_qty = sum(b.get('allocated_qty', 0) for b in selected)
                total_cost = sum(b.get('total_cost', 0) for b in selected)
                fefo_violations = self._count_fefo_violations(selected, batches)
                
                # Get earliest expiry
                expiry_dates = [b.get('expiry_date') for b in selected if b.get('expiry_date')]
                earliest_expiry = min(expiry_dates) if expiry_dates else None
                
                scenarios[strategy.value] = {
                    'selected_batches': selected,
                    'total_qty': total_qty,
                    'total_cost': round(total_cost, 2),
                    'batch_count': len(selected),
                    'fefo_violations': fefo_violations,
                    'earliest_expiry': str(earliest_expiry) if earliest_expiry else None,
                    'fulfillment_pct': round(total_qty / required_qty * 100, 1) if required_qty > 0 else 0
                }
            except Exception as e:
                self._log(f"Error in {strategy.value} scenario: {e}", level="warning")
                scenarios[strategy.value] = {
                    'error': str(e),
                    'total_cost': 0,
                    'batch_count': 0,
                    'fefo_violations': 0
                }
        
        # Build comparison
        valid_scenarios = {k: v for k, v in scenarios.items() if 'error' not in v}
        
        comparison = {}
        if valid_scenarios:
            # Find lowest cost
            lowest_cost_strategy = min(valid_scenarios.keys(), key=lambda k: valid_scenarios[k]['total_cost'])
            comparison['lowest_cost_strategy'] = lowest_cost_strategy
            comparison['lowest_cost_value'] = valid_scenarios[lowest_cost_strategy]['total_cost']
            
            # Find best FEFO (zero violations, then lowest cost)
            zero_violation_strategies = [k for k, v in valid_scenarios.items() if v['fefo_violations'] == 0]
            if zero_violation_strategies:
                best_fefo = min(zero_violation_strategies, key=lambda k: valid_scenarios[k]['total_cost'])
            else:
                best_fefo = min(valid_scenarios.keys(), key=lambda k: valid_scenarios[k]['fefo_violations'])
            comparison['best_fefo_strategy'] = best_fefo
            
            # Find fewest batches
            fewest_batches_strategy = min(valid_scenarios.keys(), key=lambda k: valid_scenarios[k]['batch_count'])
            comparison['fewest_batches_strategy'] = fewest_batches_strategy
            
            # Recommendation logic
            # Prefer balanced if it has zero violations and reasonable cost
            balanced = valid_scenarios.get('fefo_cost_balanced', {})
            strict = valid_scenarios.get('strict_fefo', {})
            min_cost = valid_scenarios.get('minimize_cost', {})
            
            if balanced.get('fefo_violations', 1) == 0:
                # Balanced has no violations - check if cost is acceptable
                cost_increase = (balanced.get('total_cost', 0) - min_cost.get('total_cost', 0)) / min_cost.get('total_cost', 1) * 100 if min_cost.get('total_cost', 0) > 0 else 0
                if cost_increase < 10:  # Less than 10% more than minimum cost
                    comparison['recommended_strategy'] = 'fefo_cost_balanced'
                    comparison['recommendation_reason'] = f'Best balance: zero FEFO violations with only {cost_increase:.1f}% cost increase vs minimum'
                else:
                    comparison['recommended_strategy'] = 'strict_fefo'
                    comparison['recommendation_reason'] = 'Strict FEFO recommended for full compliance'
            elif strict.get('fefo_violations', 1) == 0:
                comparison['recommended_strategy'] = 'strict_fefo'
                comparison['recommendation_reason'] = 'Only strategy with zero FEFO violations'
            else:
                comparison['recommended_strategy'] = 'fefo_cost_balanced'
                comparison['recommendation_reason'] = 'Best balance of FEFO compliance and cost'
        
        return {
            'scenarios': scenarios,
            'comparison': comparison
        }
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _count_fefo_violations(
        self,
        selected: List[Dict],
        available: List[Dict]
    ) -> int:
        """
        Count FEFO violations in selection.
        
        A violation occurs when a newer batch is used while an older
        batch of the same item remains unused.
        """
        if not selected or not available:
            return 0
        
        violations = 0
        selected_ids = set(b.get('batch_id') or b.get('batch_no') for b in selected)
        
        for sel_batch in selected:
            item_code = sel_batch.get('item_code')
            sel_expiry = sel_batch.get('expiry_date')
            
            if not item_code or not sel_expiry:
                continue
            
            # Find older batches of same item that weren't fully used
            for avail_batch in available:
                if avail_batch.get('item_code') != item_code:
                    continue
                
                avail_id = avail_batch.get('batch_id') or avail_batch.get('batch_no')
                if avail_id in selected_ids:
                    continue
                
                avail_expiry = avail_batch.get('expiry_date')
                avail_qty = avail_batch.get('available_qty', 0)
                
                if avail_expiry and avail_qty > 0:
                    # Compare dates
                    if str(avail_expiry) < str(sel_expiry):
                        violations += 1
        
        return violations
    
    def _get_days_to_expiry(self, batch: Dict) -> int:
        """Get days to expiry for a batch."""
        expiry = batch.get('expiry_date')
        today = date.today()
        
        if isinstance(expiry, str):
            try:
                expiry = datetime.strptime(expiry[:10], '%Y-%m-%d').date()
            except:
                return 365
        elif not isinstance(expiry, date):
            return 365
        
        return (expiry - today).days
    
    def _get_adjusted_weights(self, cost_data: Dict) -> Dict:
        """
        Adjust strategy weights based on cost trend from Phase 4.
        """
        weights = self.DEFAULT_WEIGHTS.copy()
        
        if not cost_data:
            return weights
        
        # Check for cost trend in cost_data
        trend = cost_data.get('trend', {}).get('direction', 'stable')
        
        if trend == 'increasing':
            # Costs are rising - favor older (potentially cheaper) inventory
            weights = {'fefo': 0.5, 'cost': 0.5}
        elif trend == 'decreasing':
            # Costs are falling - stronger FEFO priority (newer stock is cheaper)
            weights = {'fefo': 0.7, 'cost': 0.3}
        
        return weights
    
    def _create_empty_summary(self, strategy_name: str) -> Dict:
        """Create an empty summary structure."""
        return {
            'total_quantity': 0,
            'total_cost': 0,
            'average_unit_cost': 0,
            'batch_count': 0,
            'earliest_expiry': None,
            'fefo_violations': 0,
            'constraints_satisfied': False,
            'strategy_used': strategy_name
        }
    
    # =========================================================================
    # LEGACY ACTIONS (for backwards compatibility)
    # =========================================================================
    
    def _optimize_legacy(self, payload: Dict, message: AgentMessage) -> Dict:
        """Legacy optimize action - analyze workflow state and suggest improvements."""
        workflow_state = payload.get('workflow_state', {})
        constraints = payload.get('constraints', {})
        
        self._log("Running legacy optimization analysis")
        self.send_status("optimizing", {"constraints": list(constraints.keys())})
        
        batch_selection = workflow_state.get('phases', {}).get('batch_selection', {})
        compliance = workflow_state.get('phases', {}).get('compliance', {})
        
        recommendations = []
        optimized_selection = None
        
        if compliance and not compliance.get('passed', True):
            non_compliant = compliance.get('non_compliant_batches', [])
            tds_requirements = payload.get('tds_requirements', {})
            
            for batch in non_compliant:
                alternatives = self._find_alternatives_for_batch(
                    batch, tds_requirements, constraints
                )
                
                if alternatives:
                    recommendations.append({
                        "type": "replace_batch",
                        "original_batch": batch.get('batch_name'),
                        "alternatives": alternatives,
                        "reason": f"Non-compliant on: {', '.join(batch.get('failing_parameters', []))}"
                    })
        
        if constraints.get('minimize_cost'):
            cost_optimization = self._optimize_for_cost_legacy(
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
        """Suggest alternative batches for current selection."""
        workflow_state = payload.get('workflow_state', {})
        
        request = workflow_state.get('request', {})
        phases = workflow_state.get('phases', {})
        
        current_selection = phases.get('batch_selection', {}).get('selected_batches', [])
        compliance = phases.get('compliance', {})
        
        alternatives = []
        non_compliant = compliance.get('non_compliant_batches', [])
        
        for batch in non_compliant:
            item_code = batch.get('item_code')
            parsed = parse_golden_number(item_code)
            
            if parsed:
                available = get_available_batches(
                    product_code=parsed['product'],
                    warehouse=batch.get('warehouse', 'FG to Sell Warehouse - AMB-W')
                )
                
                current_batch_names = [b.get('batch_name') for b in current_selection]
                
                for alt_batch in available:
                    if alt_batch['batch_name'] in current_batch_names:
                        continue
                    
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
        """Optimize blend ratios to meet target specifications."""
        available_batches = payload.get('available_batches', [])
        target_spec = payload.get('target_spec', {})
        total_qty = payload.get('total_qty', 1000)
        
        if not available_batches:
            return {"error": "No batches available for blending"}
        
        blend_ratios = []
        
        for param_name, spec in target_spec.items():
            target_value = spec.get('target')
            if not target_value:
                continue
            
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
            
            if above and below:
                batch_high, value_high = above[0]
                batch_low, value_low = below[0]
                
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
        """Find all batches that comply with given TDS requirements."""
        product_code = payload.get('product_code')
        warehouse = payload.get('warehouse', 'FG to Sell Warehouse - AMB-W')
        tds_requirements = payload.get('tds_requirements', {})
        
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
    
    def _optimize_for_cost_legacy(
        self,
        current_selection: List[Dict],
        constraints: Dict
    ) -> Optional[Dict]:
        """Legacy cost optimization."""
        return None


# Import for timedelta
from datetime import timedelta

# Export for auto-discovery
AGENT_CLASS = OptimizationEngine
