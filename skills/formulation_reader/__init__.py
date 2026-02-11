"""
Formulation Reader Skill
========================

Phase 1: Data Model & Read-Only Analytics

This skill provides read-only access to ERPNext formulation data:
- Batch AMB records
- COA AMB2 parameters
- TDS specifications
- Blend simulation (weighted averages)

All operations are READ-ONLY and do not modify any ERPNext data.
"""

from raven_ai_agent.skills.formulation_reader.skill import FormulationReaderSkill
from raven_ai_agent.skills.formulation_reader.reader import (
    FormulationReader,
    # Data classes
    TDSParameter,
    TDSSpec,
    COAParameter,
    Cunete,
    BatchAMBRecord,
    BlendInput,
    BlendParameterResult,
    BlendSimulationResult,
    # Convenience functions
    get_tds_for_sales_order_item,
    get_batches_for_item_and_warehouse,
    get_coa_amb2_for_batch,
    simulate_blend,
)

# Required export for skill auto-discovery
SKILL_CLASS = FormulationReaderSkill

__all__ = [
    # Skill class
    "FormulationReaderSkill",
    "SKILL_CLASS",
    # Reader class
    "FormulationReader",
    # Data classes
    "TDSParameter",
    "TDSSpec",
    "COAParameter",
    "Cunete",
    "BatchAMBRecord",
    "BlendInput",
    "BlendParameterResult",
    "BlendSimulationResult",
    # Convenience functions
    "get_tds_for_sales_order_item",
    "get_batches_for_item_and_warehouse",
    "get_coa_amb2_for_batch",
    "simulate_blend",
]
