"""Formulation Advisor Skill - SkillBase implementation."""
import re
from typing import Dict, Optional
from ..framework import SkillBase
from .advisor import FormulationAdvisor


class FormulationAdvisorSkill(SkillBase):
    """
    Skill for suggesting optimal formulations from warehouse inventory.
    
    Responds to queries about:
    - Formulating products from available cuñetes/batches
    - Matching TDS specifications
    - Blending raw materials
    """
    
    name = "formulation-advisor"
    description = "Suggests optimal formulations from warehouse inventory to match TDS specs"
    emoji = "🧪"
    version = "1.0.0"
    priority = 60
    
    triggers = [
        "formulate",
        "formulation",
        "formulacion",
        "cuñetes",
        "cunetes",
        "tds",
        "blend",
        "mezcla",
        "match spec",
        "que lotes",
        "which batches",
        "almacen",
        "warehouse inventory"
    ]
    
    patterns = [
        r"formul\w+.*(?:item|producto|from|para)",
        r"(?:cuñetes?|cunetes?|lotes?).*(?:almacen|warehouse)",
        r"(?:match|cumpl\w+).*tds",
        r"blend.*(?:for|para)",
        r"(?:que|which).*(?:lotes|batches).*(?:pueden|can)"
    ]
    
    def __init__(self, agent=None):
        super().__init__(agent)
        self.advisor = FormulationAdvisor()
    
    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        """Handle formulation-related queries."""
        query_lower = query.lower()
        
        # Check if this query is for us
        if not self._should_handle(query_lower):
            return None
        
        # Parse the query to extract parameters
        item_code = self._extract_item(query)
        warehouse = self._extract_warehouse(query)
        quantity = self._extract_quantity(query)
        
        # Route to appropriate action
        if "batch" in query_lower or "lote" in query_lower:
            if batch_no := self._extract_batch(query):
                return self._get_batch_info(batch_no)
        
        if item_code and warehouse:
            return self._suggest_formulation(item_code, warehouse, quantity)
        
        if warehouse and not item_code:
            return self._list_warehouse_batches(warehouse)
        
        # Default: show help
        return self._show_help()
    
    def _should_handle(self, query: str) -> bool:
        """Check if query matches our triggers or patterns."""
        # Check triggers
        if any(t in query for t in self.triggers):
            return True
        
        # Check patterns
        for pattern in self.patterns:
            if re.search(pattern, query, re.IGNORECASE):
                return True
        
        return False
    
    def _extract_item(self, query: str) -> Optional[str]:
        """Extract item code from query."""
        patterns = [
            r"(?:item|producto|for|para)\s+[\"']?([A-Z0-9\-]+)[\"']?",
            r"formul\w+\s+([A-Z0-9\-]+)",
        ]
        for pattern in patterns:
            if match := re.search(pattern, query, re.IGNORECASE):
                return match.group(1).upper()
        return None
    
    def _extract_warehouse(self, query: str) -> Optional[str]:
        """Extract warehouse from query."""
        patterns = [
            r"(?:almacen|warehouse|from)\s+[\"']?([A-Za-z0-9\-\s]+?)[\"']?(?:\s|,|$)",
            r"(?:en|in)\s+(?:el\s+)?(?:almacen|warehouse)\s+[\"']?([A-Za-z0-9\-]+)",
        ]
        for pattern in patterns:
            if match := re.search(pattern, query, re.IGNORECASE):
                return match.group(1).strip()
        return "Almacen-MP"  # Default warehouse
    
    def _extract_quantity(self, query: str) -> float:
        """Extract quantity from query."""
        if match := re.search(r"(\d+(?:\.\d+)?)\s*(?:L|kg|units?|litros?)", query, re.IGNORECASE):
            return float(match.group(1))
        return 100.0  # Default quantity
    
    def _extract_batch(self, query: str) -> Optional[str]:
        """Extract batch number from query."""
        if match := re.search(r"(?:batch|lote)\s+[\"']?([A-Z0-9\-]+)[\"']?", query, re.IGNORECASE):
            return match.group(1)
        return None
    
    def _suggest_formulation(self, item_code: str, warehouse: str, quantity: float) -> Dict:
        """Suggest a formulation."""
        result = self.advisor.suggest_formulation(item_code, warehouse, quantity)
        
        if result.get("error"):
            return {
                "handled": True,
                "response": f"❌ {result['error']}",
                "confidence": 0.9
            }
        
        # Format response
        blend_lines = []
        for comp in result.get("suggested_blend", []):
            blend_lines.append(
                f"  • **{comp['item']}** ({comp['batch']}): {comp['quantity']}L"
            )
        
        blend_text = "\n".join(blend_lines) if blend_lines else "  No suitable blend found"
        
        meets = "✅" if result["final_specs"]["meets_target"] else "⚠️"
        
        response = f"""🧪 **Formulation Suggestion for {item_code}**

📦 Warehouse: {warehouse}
🎯 Target TDS: {result['target_specs']['tds_range']}
📊 Available batches: {result['available_batches']}

**Suggested Blend ({quantity}L):**
{blend_text}

**Result:**
{meets} Final TDS: {result['final_specs']['tds']} (Target: {result['target_specs']['tds_range']})
"""
        
        return {
            "handled": True,
            "response": response,
            "confidence": 0.95,
            "data": result
        }
    
    def _list_warehouse_batches(self, warehouse: str) -> Dict:
        """List available batches in warehouse."""
        batches = self.advisor.get_warehouse_batches(warehouse)
        
        if not batches:
            return {
                "handled": True,
                "response": f"📦 No batches found in {warehouse}",
                "confidence": 0.8
            }
        
        lines = [f"📦 **Batches in {warehouse}:**\n"]
        lines.append("| Batch | Item | TDS | pH | Qty | Expiry |")
        lines.append("|-------|------|-----|-----|-----|--------|")
        
        for b in batches[:10]:  # Limit to 10
            lines.append(f"| {b.batch_no} | {b.item_code} | {b.tds} | {b.ph} | {b.qty_available} | {b.expiry_date or 'N/A'} |")
        
        return {
            "handled": True,
            "response": "\n".join(lines),
            "confidence": 0.9
        }
    
    def _get_batch_info(self, batch_no: str) -> Dict:
        """Get info for a specific batch."""
        # Would query Frappe for batch details
        return {
            "handled": True,
            "response": f"🏷️ Batch **{batch_no}** details would be shown here",
            "confidence": 0.7
        }
    
    def _show_help(self) -> Dict:
        """Show help for this skill."""
        return {
            "handled": True,
            "response": """🧪 **Formulation Advisor**

**Commands:**
• `formulate ITEM-CODE from WAREHOUSE` - Suggest formulation
• `list batches in WAREHOUSE` - Show available cuñetes
• `check batch BATCH-NO` - Get batch specifications

**Example:**
> formulate CREMA-HIDRATANTE from Almacen-MP
""",
            "confidence": 0.8
        }


# Export for auto-discovery
SKILL_CLASS = FormulationAdvisorSkill
