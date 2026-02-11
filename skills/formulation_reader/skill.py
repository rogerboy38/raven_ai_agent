"""
Formulation Reader Skill - SkillBase Implementation
===================================================

This skill provides read-only access to ERPNext formulation data.
It handles natural language queries about batches, COAs, TDS specs,
blend simulations, and FEFO sorting.

Example queries supported (from spec section 5):
- "What batches do we have available for product 0612?"
- "Show me the COA parameters for batch LOTE040"
- "Which batches from 2023 still have stock?"
- "What is the oldest batch we should use first?"
"""

from raven_ai_agent.skills.framework import SkillBase
from typing import Dict, List, Optional
import re
import json


class FormulationReaderSkill(SkillBase):
    """
    Skill for reading formulation data from ERPNext.
    
    Capabilities (aligned with PHASE1_FORMULATION_READER_AGENT.md):
    - Query available batches with stock quantities (via Bin doctype)
    - Parse golden numbers from item codes for FEFO sorting
    - Retrieve COA parameters for batches (using 'specification' field)
    - Get TDS specifications for customers
    - Calculate FEFO keys for batch prioritization
    - Simulate blend weighted averages
    
    All operations are READ-ONLY.
    """
    
    name = "formulation-reader"
    description = "Read formulation data (batches, COA, TDS, FEFO sorting) and simulate blends"
    emoji = "📊"
    version = "1.1.0"  # Updated for spec alignment
    priority = 70  # Higher priority for formulation-related queries
    
    # Simple keyword triggers - updated for spec examples
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
        "product",
        "fefo",
        "oldest",
        "stock",
        "available",
        "lote",  # LOTExxxx batch naming
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
        r"product\s+\d{4}",  # Product code like 0612
        r"(oldest|newest)\s+batch",  # FEFO queries
        r"from\s+\d{4}",  # Year queries
        r"lote\d+",  # LOTE batch format
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
        
        Supported query types (from spec section 5):
        1. Get batches by product: "What batches do we have available for product 0612?"
        2. Get COA: "Show me the COA parameters for batch LOTE040"
        3. Get batches by year: "Which batches from 2023 still have stock?"
        4. Get oldest batch (FEFO): "What is the oldest batch we should use first?"
        5. Get TDS: "What are TDS specs for AL-QX-90-10 in SO-00754?"
        6. Simulate blend: "Simulate blend of 10kg from X and 15kg from Y"
        
        Returns:
            Dict with response or None if not handled
        """
        query_lower = query.lower()
        
        try:
            # Detect query type and route to appropriate handler
            if self._is_fefo_query(query_lower):
                return self._handle_fefo_query(query, context)
            
            elif self._is_batch_query(query_lower):
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
            r"what\s+batch(es)?\s+.*(have|available)",
            r"(available|stock)\s+.*batch",
            r"product\s+\d{4}",  # Product code query
            r"from\s+(20)?\d{2}\s+.*(stock|batch)",  # Year query
        ]
        return any(re.search(p, query) for p in patterns)
    
    def _is_fefo_query(self, query: str) -> bool:
        """Check if query is specifically about FEFO (oldest/newest batch)."""
        patterns = [
            r"oldest\s+batch",
            r"newest\s+batch",
            r"(first|next)\s+.*ship",
            r"fefo",
            r"use\s+first",
        ]
        return any(re.search(p, query) for p in patterns)
    
    def _is_coa_query(self, query: str) -> bool:
        """Check if query is about COA."""
        patterns = [
            r"(get|show)\s+coa",
            r"coa\s+(for|of|amb|parameter)",
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
        """
        Handle batch-related queries using spec-aligned functions.
        
        Uses get_available_batches() which queries Bin doctype and sorts by FEFO.
        """
        from raven_ai_agent.skills.formulation_reader.reader import (
            get_available_batches, parse_golden_number
        )
        
        # Extract product code (4-digit) from query
        product_code = self._extract_product_code(query)
        warehouse = self._extract_warehouse(query)
        year_filter = self._extract_year_filter(query)
        
        # Default warehouse per spec
        if not warehouse:
            warehouse = 'FG to Sell Warehouse - AMB-W'
        
        # Get batches using spec-aligned function
        batches = get_available_batches(
            product_code=product_code,
            warehouse=warehouse
        )
        
        # Filter by year if specified
        if year_filter:
            batches = [b for b in batches if b['year'] == year_filter]
        
        if not batches:
            msg = f"No batches found"
            if product_code:
                msg += f" for product '{product_code}'"
            if year_filter:
                msg += f" from year {year_filter}"
            msg += f" in warehouse '{warehouse}'."
            
            return {
                "handled": True,
                "response": msg,
                "confidence": 0.9,
                "data": {"batches": [], "product_code": product_code, "warehouse": warehouse}
            }
        
        # Format response per spec section 6
        total_qty = sum(b['qty'] for b in batches)
        oldest_fefo = min(b['fefo_key'] for b in batches)
        newest_fefo = max(b['fefo_key'] for b in batches)
        
        response_lines = [
            "[FORMULATION_READER RESPONSE]\n",
            f"Query: Available batches" + (f" for product {product_code}" if product_code else "") + (f" from {year_filter}" if year_filter else ""),
            "\nResults (sorted by FEFO - oldest first):",
        ]
        
        for batch in batches:
            response_lines.append(
                f"- **{batch['item_code']}** (Batch: {batch['batch_name'] or 'N/A'}): "
                f"{batch['qty']} kg, FEFO Key: {batch['fefo_key']} (Year: {batch['year']}, Folio: {batch['folio']})"
            )
        
        response_lines.extend([
            "\nSummary:",
            f"- Total batches found: {len(batches)}",
            f"- Total quantity available: {total_qty} Kg",
            f"- FEFO range: {oldest_fefo} to {newest_fefo}",
        ])
        
        return {
            "handled": True,
            "response": "\n".join(response_lines),
            "confidence": 0.95,
            "data": {
                "batches": batches,
                "product_code": product_code,
                "warehouse": warehouse,
                "total_qty": total_qty,
                "fefo_range": {"oldest": oldest_fefo, "newest": newest_fefo},
            }
        }
    
    def _handle_fefo_query(self, query: str, context: Dict = None) -> Dict:
        """
        Handle FEFO-specific queries (oldest/newest batch).
        
        Spec example 5.4: "What is the oldest batch we should use first?"
        """
        from raven_ai_agent.skills.formulation_reader.reader import get_available_batches
        
        product_code = self._extract_product_code(query)
        warehouse = self._extract_warehouse(query) or 'FG to Sell Warehouse - AMB-W'
        
        # Get batches sorted by FEFO
        batches = get_available_batches(product_code=product_code, warehouse=warehouse)
        
        if not batches:
            return {
                "handled": True,
                "response": "No batches with stock found.",
                "confidence": 0.9,
                "data": {"batches": []}
            }
        
        # Determine if asking for oldest or newest
        is_newest = 'newest' in query.lower()
        target_batch = batches[-1] if is_newest else batches[0]  # Already sorted by FEFO
        
        batch_type = "newest" if is_newest else "oldest"
        
        response = f"""[FORMULATION_READER RESPONSE]

Query: {batch_type.capitalize()} batch to use {'last' if is_newest else 'first'}

Result:
- **Item Code**: {target_batch['item_code']}
- **Batch Name**: {target_batch['batch_name'] or 'N/A'}
- **Quantity Available**: {target_batch['qty']} kg
- **Warehouse**: {target_batch['warehouse']}
- **Year**: {target_batch['year']}
- **Folio**: {target_batch['folio']}
- **FEFO Key**: {target_batch['fefo_key']} ({'lowest - ship first' if not is_newest else 'highest - ship last'})

Summary:
- This is the {batch_type} batch and should be {'shipped first' if not is_newest else 'shipped last'} per FEFO policy."""
        
        return {
            "handled": True,
            "response": response,
            "confidence": 0.95,
            "data": {
                "batch": target_batch,
                "batch_type": batch_type,
            }
        }
    
    def _handle_coa_query(self, query: str, context: Dict = None) -> Dict:
        """
        Handle COA-related queries using spec-aligned function.
        
        Spec example 5.2: "Show me the COA parameters for batch LOTE040"
        Uses get_batch_coa_parameters() which queries 'specification' field.
        """
        from raven_ai_agent.skills.formulation_reader.reader import get_batch_coa_parameters
        
        # Extract batch name from query (supports LOTE format)
        batch_name = self._extract_batch_name(query)
        
        if not batch_name:
            return {
                "handled": True,
                "response": "Please specify a batch name. Example: 'Show me the COA parameters for batch LOTE040'",
                "confidence": 0.7,
            }
        
        # Get COA parameters using spec-aligned function
        parameters = get_batch_coa_parameters(batch_name)
        
        if not parameters:
            return {
                "handled": True,
                "response": f"Could not find COA for batch {batch_name}. This batch may not have quality testing completed yet. Please verify with Quality team.",
                "confidence": 0.9,
                "data": {"parameters": None, "batch_name": batch_name}
            }
        
        # Format response per spec section 6
        response_lines = [
            "[FORMULATION_READER RESPONSE]\n",
            f"Query: COA parameters for batch {batch_name}",
            "\nResults:",
        ]
        
        for param_name, param_data in parameters.items():
            status_icon = "✅" if param_data['status'] == "PASS" else "❌" if param_data['status'] == "FAIL" else "➖"
            value_str = f"{param_data['value']}" if param_data['value'] is not None else "N/A"
            range_str = ""
            if param_data.get('min') is not None and param_data.get('max') is not None:
                range_str = f" (Range: {param_data['min']}-{param_data['max']})"
            elif param_data.get('max') is not None:
                range_str = f" (Max: {param_data['max']})"
            elif param_data.get('min') is not None:
                range_str = f" (Min: {param_data['min']})"
            
            response_lines.append(
                f"- {status_icon} **{param_name}**: {value_str}{range_str} [{param_data['status']}]"
            )
        
        response_lines.extend([
            "\nSummary:",
            f"- Total parameters: {len(parameters)}",
        ])
        
        return {
            "handled": True,
            "response": "\n".join(response_lines),
            "confidence": 0.95,
            "data": {
                "parameters": parameters,
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

**1. Query Available Batches (with FEFO sorting):**
> "What batches do we have available for product 0612?"
> "Which batches from 2023 still have stock?"

**2. Get Oldest/Newest Batch (FEFO):**
> "What is the oldest batch we should use first?"
> "What is the newest batch?"

**3. Read COA Parameters:**
> "Show me the COA parameters for batch LOTE040"
> "Get COA for batch LOTE001"

**4. Get TDS Specifications:**
> "What are TDS specs for AL-QX-90-10?"
> "Get TDS for item AL-QX-90-10 in SO-00754"

**5. Simulate Blend:**
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
    
    def _extract_product_code(self, query: str) -> Optional[str]:
        """Extract 4-digit product code from query (e.g., 0612, 0616)."""
        patterns = [
            r'product\s+(\d{4})',  # "product 0612"
            r'for\s+(\d{4})',  # "for 0612"
            r'(\d{4})\s+batches',  # "0612 batches"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_year_filter(self, query: str) -> Optional[int]:
        """Extract year filter from query (e.g., 2023, from 23)."""
        patterns = [
            r'from\s+(20)?(\d{2})\b',  # "from 2023" or "from 23"
            r'(20\d{2})\s+.*(stock|batch)',  # "2023 stock"
            r'year\s+(20)?(\d{2})',  # "year 2023"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                groups = match.groups()
                # Handle both 2023 and 23 formats
                if groups[-1]:
                    year = int(groups[-1])
                    return 2000 + year if year < 100 else year
        
        return None
    
    def _extract_item_code(self, query: str) -> Optional[str]:
        """Extract item code from query (for TDS and blend queries)."""
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
            r'in\s+(FG[A-Za-z0-9\s-]+Warehouse[A-Za-z0-9\s-]*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _extract_batch_name(self, query: str) -> Optional[str]:
        """Extract batch name from query (supports LOTE format per spec)."""
        patterns = [
            r'batch\s+(LOTE\d+)',  # LOTE040 format (per spec)
            r'(LOTE\d+)',  # LOTE anywhere
            r'batch\s+([A-Z0-9-]+AMB[A-Z0-9-]+)',
            r'batch\s+([A-Z0-9-]{5,})',
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
