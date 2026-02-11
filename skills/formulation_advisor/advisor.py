"""Formulation Advisor - Suggests optimal formulations from warehouse inventory."""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class BatchSpec:
    """Specifications for a batch/cuñete."""
    batch_no: str
    item_code: str
    qty_available: float
    warehouse: str
    expiry_date: str = None
    # Spec fields
    tds: float = 0.0
    ph: float = 7.0
    viscosity: float = 0.0
    density: float = 1.0
    purity: float = 100.0
    moisture: float = 0.0
    lote_proveedor: str = ""


@dataclass
class TargetSpec:
    """Target specifications for a product."""
    item_code: str
    tds_min: float = 0.0
    tds_max: float = 100.0
    ph_min: float = 0.0
    ph_max: float = 14.0
    viscosity_min: float = 0.0
    viscosity_max: float = 10000.0


@dataclass
class BlendComponent:
    """A component in a suggested blend."""
    batch_no: str
    item_code: str
    quantity: float
    contribution: Dict[str, float]  # spec_name -> contribution


class FormulationAdvisor:
    """
    Advises on optimal formulations based on warehouse inventory.
    
    The core problem:
    Given: Available batches (cuñetes) with known specs
    Target: A product TDS/specification
    Find: Optimal blend of batches to meet target
    """
    
    def __init__(self):
        self.frappe = None
        try:
            import frappe
            self.frappe = frappe
        except ImportError:
            pass
    
    def get_warehouse_batches(self, warehouse: str, item_code: str = None) -> List[BatchSpec]:
        """Get all available batches in a warehouse."""
        if not self.frappe:
            return self._mock_batches(warehouse, item_code)
        
        filters = {"warehouse": warehouse, "actual_qty": [">", 0]}
        if item_code:
            filters["item_code"] = item_code
        
        # Get stock with batch info
        stock_entries = self.frappe.get_all(
            "Stock Ledger Entry",
            filters=filters,
            fields=["batch_no", "item_code", "actual_qty", "warehouse"],
            group_by="batch_no"
        )
        
        batches = []
        for entry in stock_entries:
            if not entry.batch_no:
                continue
            
            # Get batch details with custom fields
            batch_doc = self.frappe.get_doc("Batch", entry.batch_no)
            
            batches.append(BatchSpec(
                batch_no=entry.batch_no,
                item_code=entry.item_code,
                qty_available=entry.actual_qty,
                warehouse=entry.warehouse,
                expiry_date=str(batch_doc.expiry_date) if batch_doc.expiry_date else None,
                tds=float(batch_doc.get("custom_tds_value") or 0),
                ph=float(batch_doc.get("custom_ph_level") or 7),
                viscosity=float(batch_doc.get("custom_viscosity") or 0),
                density=float(batch_doc.get("custom_density") or 1),
                purity=float(batch_doc.get("custom_purity") or 100),
                moisture=float(batch_doc.get("custom_moisture") or 0),
                lote_proveedor=batch_doc.get("custom_lote_proveedor") or ""
            ))
        
        return batches
    
    def get_item_target_specs(self, item_code: str) -> Optional[TargetSpec]:
        """Get target specifications for an item."""
        if not self.frappe:
            return self._mock_target_spec(item_code)
        
        item = self.frappe.get_doc("Item", item_code)
        
        return TargetSpec(
            item_code=item_code,
            tds_min=float(item.get("custom_tds_min") or 0),
            tds_max=float(item.get("custom_tds_max") or 100),
            ph_min=float(item.get("custom_ph_min") or 0),
            ph_max=float(item.get("custom_ph_max") or 14),
            viscosity_min=float(item.get("custom_viscosity_min") or 0),
            viscosity_max=float(item.get("custom_viscosity_max") or 10000)
        )
    
    def find_matching_batches(self, batches: List[BatchSpec], target: TargetSpec) -> List[BatchSpec]:
        """Find batches that can contribute to matching target specs."""
        matching = []
        for batch in batches:
            # A batch is useful if its specs are within reasonable range
            # Even if outside target, it might blend well with others
            if batch.qty_available > 0:
                matching.append(batch)
        
        # Sort by expiry date (FIFO) and then by how close to target
        matching.sort(key=lambda b: (b.expiry_date or "9999-12-31", abs(b.tds - (target.tds_min + target.tds_max) / 2)))
        
        return matching
    
    def calculate_blend(self, batches: List[BatchSpec], target: TargetSpec, 
                       total_quantity: float) -> List[BlendComponent]:
        """
        Calculate optimal blend proportions to meet target specs.
        
        Uses weighted average principle:
        final_spec = Σ(qty_i × spec_i) / Σ(qty_i)
        """
        if not batches:
            return []
        
        # Simple linear optimization for TDS target
        target_tds = (target.tds_min + target.tds_max) / 2
        target_ph = (target.ph_min + target.ph_max) / 2
        
        # Sort batches by TDS to enable blending strategy
        sorted_batches = sorted(batches, key=lambda b: b.tds)
        
        # Find batches above and below target for blending
        below_target = [b for b in sorted_batches if b.tds <= target_tds]
        above_target = [b for b in sorted_batches if b.tds > target_tds]
        
        components = []
        remaining_qty = total_quantity
        
        # Strategy: Blend high and low TDS batches to hit target
        if below_target and above_target:
            low_batch = below_target[-1]  # Highest of the low
            high_batch = above_target[0]   # Lowest of the high
            
            # Calculate blend ratio: target = (q1*tds1 + q2*tds2) / (q1+q2)
            # Solve for q1/q2 ratio
            if high_batch.tds != low_batch.tds:
                ratio = (high_batch.tds - target_tds) / (target_tds - low_batch.tds)
                q_low = total_quantity * ratio / (1 + ratio)
                q_high = total_quantity - q_low
                
                # Clamp to available quantities
                q_low = min(q_low, low_batch.qty_available)
                q_high = min(q_high, high_batch.qty_available)
                
                if q_low > 0:
                    components.append(BlendComponent(
                        batch_no=low_batch.batch_no,
                        item_code=low_batch.item_code,
                        quantity=round(q_low, 2),
                        contribution={"tds": round(q_low * low_batch.tds / total_quantity, 2)}
                    ))
                
                if q_high > 0:
                    components.append(BlendComponent(
                        batch_no=high_batch.batch_no,
                        item_code=high_batch.item_code,
                        quantity=round(q_high, 2),
                        contribution={"tds": round(q_high * high_batch.tds / total_quantity, 2)}
                    ))
        
        elif batches:
            # Use single best batch
            best = min(batches, key=lambda b: abs(b.tds - target_tds))
            qty = min(total_quantity, best.qty_available)
            components.append(BlendComponent(
                batch_no=best.batch_no,
                item_code=best.item_code,
                quantity=round(qty, 2),
                contribution={"tds": round(best.tds, 2)}
            ))
        
        return components
    
    def suggest_formulation(self, item_code: str, warehouse: str, 
                           quantity: float = 100.0) -> Dict[str, Any]:
        """
        Main entry point: Suggest a formulation for an item using warehouse inventory.
        """
        # Get target specs
        target = self.get_item_target_specs(item_code)
        if not target:
            return {"error": f"No specifications found for item {item_code}"}
        
        # Get available batches
        batches = self.get_warehouse_batches(warehouse)
        if not batches:
            return {"error": f"No batches available in warehouse {warehouse}"}
        
        # Find matching batches
        matching = self.find_matching_batches(batches, target)
        
        # Calculate optimal blend
        blend = self.calculate_blend(matching, target, quantity)
        
        # Calculate final specs
        if blend:
            total_qty = sum(c.quantity for c in blend)
            final_tds = sum(
                c.quantity * next((b.tds for b in batches if b.batch_no == c.batch_no), 0)
                for c in blend
            ) / total_qty if total_qty > 0 else 0
        else:
            final_tds = 0
        
        return {
            "status": "success",
            "item_code": item_code,
            "warehouse": warehouse,
            "target_quantity": quantity,
            "target_specs": {
                "tds_range": f"{target.tds_min}-{target.tds_max}",
                "ph_range": f"{target.ph_min}-{target.ph_max}"
            },
            "available_batches": len(matching),
            "suggested_blend": [
                {
                    "batch": c.batch_no,
                    "item": c.item_code,
                    "quantity": c.quantity,
                    "contribution": c.contribution
                }
                for c in blend
            ],
            "final_specs": {
                "tds": round(final_tds, 2),
                "meets_target": target.tds_min <= final_tds <= target.tds_max
            }
        }
    
    def _mock_batches(self, warehouse: str, item_code: str = None) -> List[BatchSpec]:
        """Mock data for testing without Frappe."""
        return [
            BatchSpec("CU-001", "GLICERINA", 50, warehouse, "2026-06-01", tds=12.5, ph=7.0),
            BatchSpec("CU-002", "AGUA-DESMIN", 200, warehouse, "2026-12-01", tds=0.5, ph=6.8),
            BatchSpec("CU-003", "EMULSIONANTE", 25, warehouse, "2026-03-01", tds=8.2, ph=7.2),
            BatchSpec("CU-004", "GLICERINA", 30, warehouse, "2026-04-01", tds=11.8, ph=7.1),
        ]
    
    def _mock_target_spec(self, item_code: str) -> TargetSpec:
        """Mock target specs for testing."""
        return TargetSpec(item_code, tds_min=4.0, tds_max=6.0, ph_min=6.5, ph_max=7.5)
