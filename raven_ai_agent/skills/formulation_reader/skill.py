"""
Formulation Reader Skill - SkillBase Implementation
===================================================

This skill provides read-only access to ERPNext formulation data.
It handles natural language queries about batches, COAs, TDS specs,
and blend simulations.
"""

from raven_ai_agent.skills.framework import SkillBase
from typing import Dict, List, Optional
import re
import json


class FormulationReaderSkill(SkillBase):
    """
    Skill for reading formulation data from ERPNext.
    
    Capabilities:
    - Read Batch AMB records
    - Read COA AMB2 parameters
    - Get TDS specifications
    - Simulate blend weighted averages
    
    All operations are READ-ONLY.
    """
    
    name = "formulation-reader"
    description = "Read formulation data (Batch AMB, COA, TDS) and simulate blends"
    emoji = "📊"
    version = "1.0.0"
    priority = 70  # Higher priority for formulation-related queries
    
    # Simple keyword triggers
    triggers = [
        "batch",
        "batches",
        "cunete",
        "cunetes",
        "coa",
        "tds",
        "formulation",
        "blend",
        "simulate",
        "weighted average",
        "analytical",
        "parameters",
        "ph",
        "polysaccharides",
        "ash",
        "almacen",
        "warehouse",
    ]
    
    # Regex patterns for more specific matching
    patterns = [
        r"show\s+(all\s+)?batch(es)?",
        r"get\s+(coa|tds|batch)",
        r"simulate\s+(a\s+)?blend",
        r"weighted\s+average",
        r"for\s+item\s+\w+",
        r"in\s+warehouse\s+\w+",
        r"sales\s+order\s+so-\d+",
        r"batch\s+amb",
        r"coa\s+amb",
        r"al-?[a-z]+-?\d+-?\d*",  # Item code pattern like AL-QX-90-10
    ]
    
    def __init__(self, agent=None):
        super().__init__(agent)
        self._reader = None
    
    @property
    def reader(self):
        """Lazy load the FormulationReader."""
        if self._reader is None:
            from raven_ai_agent.skills.formulation_reader.reader import FormulationReader
            self._reader = FormulationReader()
        return self._reader
    
    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        """
        Handle formulation-related queries.
        
        Supported query types:
        1. Get batches: "Show batches for item X in warehouse Y"
        2. Get COA: "Get COA for batch BATCH-AMB-001"
        3. Get TDS: "What are TDS specs for AL-QX-90-10 in SO-00754?"
        4. Simulate blend: "Simulate blend of 10kg from X and 15kg from Y"
        
        Returns:
            Dict with response or None if not handled
        """
        query_lower = query.lower()
        
        try:
            # Detect query type and route to appropriate handler
            if self._is_batch_query(query_lower):
                return self._handle_batch_query(query, context)
            
            elif self._is_coa_query(query_lower):
                return self._handle_coa_query(query, context)
            
            elif self._is_tds_query(query_lower):
                return self._handle_tds_query(query, context)
            
            elif self._is_blend_query(query_lower):
                return self._handle_blend_query(query, context)
            
            # Generic formulation query - provide help
            elif any(t in query_lower for t in ["formulation", "help", "what can"]):
                return self._handle_help_query(query, context)
            
        except Exception as e:
            import frappe
            frappe.log_error(
                f"Error in FormulationReaderSkill: {str(e)}",
                "FormulationReaderSkill.handle"
            )
            return {
                "handled": True,
                "response": f"Error processing query: {str(e)}",
                "confidence": 0.5,
                "data": {"error": str(e)}
            }
        
        return None
    
    # -------------------------------------------
    # Query Type Detection
    # -------------------------------------------
    
    def _is_batch_query(self, query: str) -> bool:
        """Check if query is about batches."""
        patterns = [
            r"(show|get|list|find)\s+.*batch",
            r"batch(es)?\s+(for|in|from)",
            r"cunete",
            r"inventory\s+for",
        ]
        return any(re.search(p, query) for p in patterns)
    
    def _is_coa_query(self, query: str) -> bool:
        """Check if query is about COA."""
        patterns = [
            r"(get|show|read)\s+coa",
            r"coa\s+(for|of|amb)",
            r"analytical\s+(data|parameters|results)",
            r"(ph|polysaccharides|ash|color)\s+(for|of|value)",
        ]
        return any(re.search(p, query) for p in patterns)
    
    def _is_tds_query(self, query: str) -> bool:
        """Check if query is about TDS specifications."""
        patterns = [
            r"(get|show|what)\s+.*tds",
            r"tds\s+(for|spec|range)",
            r"specification(s)?\s+for",
            r"(min|max|range)\s+.*parameter",
        ]
        return any(re.search(p, query) for p in patterns)
    
    def _is_blend_query(self, query: str) -> bool:
        """Check if query is about blend simulation."""
        patterns = [
            r"simulate\s+(a\s+)?blend",
            r"blend\s+(of|with|from)",
            r"weighted\s+average",
            r"predict\s+.*parameter",
            r"\d+\s*kg\s+(from|of)",
        ]
        return any(re.search(p, query) for p in patterns)
    
    # -------------------------------------------
    # Query Handlers
    # -------------------------------------------
    
    def _handle_batch_query(self, query: str, context: Dict = None) -> Dict:
        """Handle batch-related queries."""
        # Extract item code and warehouse from query
        item_code = self._extract_item_code(query)
        warehouse = self._extract_warehouse(query)
        
        if not item_code:
            return {
                "handled": True,
                "response": "Please specify an item code. Example: 'Show batches for item 0227-0303 in Almacen-MP'",
                "confidence": 0.7,
            }
        
        if not warehouse:
            return {
                "handled": True,
                "response": f"Please specify a warehouse. Example: 'Show batches for item {item_code} in Almacen-MP'",
                "confidence": 0.7,
            }
        
        # Get batches
        batches = self.reader.get_batches_for_item_and_warehouse(
            item_code, warehouse, include_cunetes=True
        )
        
        if not batches:
            return {
                "handled": True,
                "response": f"No batches found for item '{item_code}' in warehouse '{warehouse}'.",
                "confidence": 0.9,
                "data": {"batches": [], "item_code": item_code, "warehouse": warehouse}
            }
        
        # Format response
        response_lines = [
            f"**Batches for {item_code} in {warehouse}:**\n",
            f"Found {len(batches)} batch(es):\n"
        ]
        
        for batch in batches:
            cunete_count = len(batch.cunetes)
            response_lines.append(
                f"- **{batch.name}**: {batch.kilos} kg, "
                f"Lot {batch.lot}/{batch.sublot}, "
                f"{cunete_count} cunete(s), "
                f"Date: {batch.manufacturing_date or 'N/A'}"
            )
        
        return {
            "handled": True,
            "response": "\n".join(response_lines),
            "confidence": 0.95,
            "data": {
                "batches": [self._batch_to_dict(b) for b in batches],
                "item_code": item_code,
                "warehouse": warehouse,
            }
        }
    
    def _handle_coa_query(self, query: str, context: Dict = None) -> Dict:
        """Handle COA-related queries."""
        # Extract batch name from query
        batch_name = self._extract_batch_name(query)
        
        if not batch_name:
            return {
                "handled": True,
                "response": "Please specify a batch name. Example: 'Get COA for batch BATCH-AMB-2024-001'",
                "confidence": 0.7,
            }
        
        # Get COA parameters
        parameters = self.reader.get_coa_amb2_for_batch(batch_name)
        
        if not parameters:
            return {
                "handled": True,
                "response": f"No COA data found for batch '{batch_name}'.",
                "confidence": 0.9,
                "data": {"parameters": [], "batch_name": batch_name}
            }
        
        # Format response
        response_lines = [
            f"**COA Parameters for {batch_name}:**\n"
        ]
        
        for param in parameters:
            status_icon = "✅" if param.result == "PASS" else "❌" if param.result == "FAIL" else "➖"
            value_str = f"{param.average or param.measured_value or 'N/A'}"
            range_str = ""
            if param.min_value is not None and param.max_value is not None:
                range_str = f" (Range: {param.min_value}-{param.max_value})"
            
            response_lines.append(
                f"- {status_icon} **{param.parameter_name}**: {value_str}{range_str} [{param.result}]"
            )
        
        return {
            "handled": True,
            "response": "\n".join(response_lines),
            "confidence": 0.95,
            "data": {
                "parameters": [self._param_to_dict(p) for p in parameters],
                "batch_name": batch_name,
            }
        }
    
    def _handle_tds_query(self, query: str, context: Dict = None) -> Dict:
        """Handle TDS-related queries."""
        # Extract item code and sales order from query
        item_code = self._extract_item_code(query)
        so_name = self._extract_sales_order(query)
        
        if not item_code:
            return {
                "handled": True,
                "response": "Please specify an item code. Example: 'Get TDS for AL-QX-90-10 in SO-00754'",
                "confidence": 0.7,
            }
        
        # Get TDS specifications
        if so_name:
            tds_spec = self.reader.get_tds_for_sales_order_item(so_name, item_code)
        else:
            tds_spec = self.reader._get_item_tds(item_code)
        
        if not tds_spec.parameters:
            return {
                "handled": True,
                "response": f"No TDS specifications found for item '{item_code}'.",
                "confidence": 0.9,
                "data": {"tds": None, "item_code": item_code}
            }
        
        # Format response
        response_lines = [
            f"**TDS Specifications for {item_code}:**\n",
            f"Source: {tds_spec.source}",
        ]
        
        if tds_spec.customer:
            response_lines.append(f"Customer: {tds_spec.customer}")
        
        response_lines.append("\n**Parameters:**")
        
        for param in tds_spec.parameters:
            range_str = f"{param.min_value or '-'} to {param.max_value or '-'}"
            nominal_str = f" (Nominal: {param.nominal_value})" if param.nominal_value else ""
            critical_str = " 🔴" if param.is_critical else ""
            
            response_lines.append(
                f"- **{param.parameter_name}**: {range_str}{nominal_str}{critical_str}"
            )
        
        return {
            "handled": True,
            "response": "\n".join(response_lines),
            "confidence": 0.95,
            "data": {
                "tds": self._tds_to_dict(tds_spec),
                "item_code": item_code,
                "sales_order": so_name,
            }
        }
    
    def _handle_blend_query(self, query: str, context: Dict = None) -> Dict:
        """Handle blend simulation queries."""
        # Extract blend inputs from query
        blend_inputs = self._extract_blend_inputs(query)
        target_item = self._extract_item_code(query)
        
        if not blend_inputs:
            return {
                "handled": True,
                "response": (
                    "Please specify blend inputs. Example:\n"
                    "'Simulate blend of 10 kg from BATCH-001-C1 and 15 kg from BATCH-002-C1 "
                    "for item AL-QX-90-10'"
                ),
                "confidence": 0.7,
            }
        
        if not target_item:
            return {
                "handled": True,
                "response": "Please specify a target item code for the blend simulation.",
                "confidence": 0.7,
            }
        
        # Perform simulation
        from raven_ai_agent.skills.formulation_reader.reader import BlendInput
        inputs = [BlendInput(**inp) for inp in blend_inputs]
        result = self.reader.simulate_blend(inputs, target_item)
        
        return {
            "handled": True,
            "response": result.summary,
            "confidence": 0.95,
            "data": self._simulation_to_dict(result)
        }
    
    def _handle_help_query(self, query: str, context: Dict = None) -> Dict:
        """Handle help/capability queries."""
        response = """**📊 Formulation Reader - Available Commands:**

**1. Read Batch Data:**
> "Show batches for item 0227-0303 in Almacen-MP"
> "List all cunetes for item AL-QX-90-10 in warehouse WH-001"

**2. Read COA Parameters:**
> "Get COA for batch BATCH-AMB-2024-001"
> "Show analytical parameters for batch X"

**3. Get TDS Specifications:**
> "What are TDS specs for AL-QX-90-10?"
> "Get TDS for item AL-QX-90-10 in SO-00754"

**4. Simulate Blend:**
> "Simulate blend of 10 kg from BATCH-001-C1 and 15 kg from BATCH-002-C1 for AL-QX-90-10"

All operations are **read-only** and do not modify any ERPNext data."""

        return {
            "handled": True,
            "response": response,
            "confidence": 0.95,
        }
    
    # -------------------------------------------
    # Extraction Helpers
    # -------------------------------------------
    
    def _extract_item_code(self, query: str) -> Optional[str]:
        """Extract item code from query."""
        # Pattern for item codes like AL-QX-90-10, 0227-0303
        patterns = [
            r'item\s+([A-Z0-9]+-[A-Z0-9]+-[0-9]+-[0-9]+)',  # AL-QX-90-10
            r'item\s+(\d{4}-\d{4})',  # 0227-0303
            r'item\s+([A-Z0-9-]+)',  # Generic
            r'for\s+([A-Z0-9]+-[A-Z0-9]+-[0-9]+-[0-9]+)',  # for AL-QX-90-10
            r'([A-Z]{2}-[A-Z]+-\d+-\d+)',  # AL-QX-90-10 anywhere
            r'(\d{4}-\d{4})',  # 0227-0303 anywhere
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        return None
    
    def _extract_warehouse(self, query: str) -> Optional[str]:
        """Extract warehouse from query."""
        patterns = [
            r'warehouse\s+([A-Za-z0-9-]+)',
            r'in\s+(Almacen[A-Za-z0-9-]*)',
            r'in\s+(WH-[A-Za-z0-9-]+)',
            r'from\s+(Almacen[A-Za-z0-9-]*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_batch_name(self, query: str) -> Optional[str]:
        """Extract batch name from query."""
        patterns = [
            r'batch\s+([A-Z0-9-]+AMB[A-Z0-9-]+)',
            r'batch\s+([A-Z0-9-]{10,})',
            r'(BATCH-AMB-[A-Z0-9-]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        return None
    
    def _extract_sales_order(self, query: str) -> Optional[str]:
        """Extract sales order name from query."""
        patterns = [
            r'(SO-\d+)',
            r'sales\s+order\s+(\w+-?\d+)',
            r'order\s+(SO\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        return None
    
    def _extract_blend_inputs(self, query: str) -> List[Dict]:
        """Extract blend inputs (cunete_id, mass_kg) from query."""
        inputs = []
        
        # Pattern: "X kg from BATCH-ID"
        pattern = r'(\d+(?:\.\d+)?)\s*kg\s+(?:from|of)\s+([A-Z0-9-]+)'
        matches = re.findall(pattern, query, re.IGNORECASE)
        
        for mass, cunete_id in matches:
            inputs.append({
                "cunete_id": cunete_id.upper(),
                "mass_kg": float(mass)
            })
        
        return inputs
    
    # -------------------------------------------
    # Serialization Helpers
    # -------------------------------------------
    
    def _batch_to_dict(self, batch) -> Dict:
        """Convert BatchAMBRecord to dict."""
        return {
            "name": batch.name,
            "product": batch.product,
            "subproduct": batch.subproduct,
            "lot": batch.lot,
            "sublot": batch.sublot,
            "kilos": batch.kilos,
            "brix": batch.brix,
            "total_solids": batch.total_solids,
            "manufacturing_date": batch.manufacturing_date,
            "warehouse": batch.warehouse,
            "cunete_count": len(batch.cunetes),
        }
    
    def _param_to_dict(self, param) -> Dict:
        """Convert COAParameter to dict."""
        return {
            "parameter_code": param.parameter_code,
            "parameter_name": param.parameter_name,
            "measured_value": param.measured_value,
            "average": param.average,
            "min_value": param.min_value,
            "max_value": param.max_value,
            "result": param.result,
        }
    
    def _tds_to_dict(self, tds) -> Dict:
        """Convert TDSSpec to dict."""
        return {
            "item_code": tds.item_code,
            "customer": tds.customer,
            "sales_order": tds.sales_order,
            "source": tds.source,
            "parameters": [
                {
                    "parameter_code": p.parameter_code,
                    "parameter_name": p.parameter_name,
                    "min_value": p.min_value,
                    "max_value": p.max_value,
                    "nominal_value": p.nominal_value,
                    "is_critical": p.is_critical,
                }
                for p in tds.parameters
            ]
        }
    
    def _simulation_to_dict(self, result) -> Dict:
        """Convert BlendSimulationResult to dict."""
        return {
            "target_item": result.target_item,
            "total_mass_kg": result.total_mass_kg,
            "all_pass": result.all_pass,
            "cunetes_used": result.cunetes_used,
            "parameters": [
                {
                    "parameter_code": p.parameter_code,
                    "parameter_name": p.parameter_name,
                    "predicted_value": p.predicted_value,
                    "tds_min": p.tds_min,
                    "tds_max": p.tds_max,
                    "result": p.result,
                }
                for p in result.parameters
            ]
        }


# Export for auto-discovery
SKILL_CLASS = FormulationReaderSkill
