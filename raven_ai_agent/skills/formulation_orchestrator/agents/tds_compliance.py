"""
TDS Compliance Agent - Phase 3
==============================

Validates batch selections against Technical Data Sheet specifications.
"""

import frappe
from typing import Dict, List, Any, Optional

from .base import BaseSubAgent
from ..messages import AgentMessage, WorkflowPhase, AgentChannel

from ...formulation_reader.reader import (
    get_batch_coa_parameters,
    check_tds_compliance
)


class TDSComplianceAgent(BaseSubAgent):
    """
    TDS Compliance Agent (Phase 3 of workflow).
    
    Responsibilities:
    - Validate batches against TDS specifications
    - Report compliance status per parameter
    - Identify non-compliant parameters
    - Suggest alternatives for non-compliant batches
    """
    
    name = "tds_compliance"
    description = "TDS specification compliance validation"
    emoji = "✅"
    phase = WorkflowPhase.TDS_COMPLIANCE
    
    def process(self, action: str, payload: Dict, message: AgentMessage) -> Optional[Dict]:
        """Route to specific action handler."""
        actions = {
            "validate_compliance": self._validate_compliance,
            "check_batch": self._check_single_batch,
            "compare_specs": self._compare_specs,
            "get_compliance_report": self._get_compliance_report,
        }
        
        handler = actions.get(action)
        if handler:
            return handler(payload, message)
        return None
    
    def _validate_compliance(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Validate a set of batches against TDS specifications.
        
        Args (in payload):
            batches: List of batch selections [{batch_name, qty, ...}]
            tds_requirements: TDS spec {param_name: {min, max}}
            
        Returns:
            Dict with passed (bool), compliant_batches, non_compliant_batches, summary
        """
        batches = payload.get('batches', [])
        tds_requirements = payload.get('tds_requirements', {})
        
        self._log(f"Validating {len(batches)} batches against TDS")
        self.send_status("validating", {"batch_count": len(batches)})
        
        compliant = []
        non_compliant = []
        
        for batch in batches:
            batch_name = batch.get('batch_name')
            if not batch_name:
                non_compliant.append({
                    **batch,
                    "status": "INVALID",
                    "reason": "No batch name provided"
                })
                continue
            
            # Get COA parameters
            coa_params = get_batch_coa_parameters(batch_name)
            
            if not coa_params:
                non_compliant.append({
                    **batch,
                    "status": "NO_COA",
                    "reason": "No COA found for batch"
                })
                continue
            
            # Check compliance
            compliance = check_tds_compliance(coa_params, tds_requirements)
            
            if compliance['all_pass']:
                compliant.append({
                    **batch,
                    "status": "COMPLIANT",
                    "parameters": compliance['parameters']
                })
            else:
                # Find failing parameters
                failing = [
                    param for param, result in compliance['parameters'].items()
                    if result['status'] not in ['PASS']
                ]
                
                non_compliant.append({
                    **batch,
                    "status": "NON_COMPLIANT",
                    "failing_parameters": failing,
                    "parameters": compliance['parameters']
                })
        
        # If no TDS requirements, treat all batches as compliant (skip COA check)
        if not tds_requirements:
            all_pass = True
            compliant = [{**b, "status": "NO_REQUIREMENTS", "parameters": {}} for b in batches]
            non_compliant = []
        else:
            all_pass = len(non_compliant) == 0 and len(compliant) > 0
        
        # Count NO_COA batches separately
        no_coa_count = sum(1 for b in non_compliant if b.get('status') == 'NO_COA')
        
        self.send_status("completed", {
            "passed": all_pass,
            "compliant_count": len(compliant),
            "non_compliant_count": len(non_compliant),
            "no_coa_count": no_coa_count
        })
        
        return {
            "passed": all_pass,
            "compliant_batches": compliant,
            "non_compliant_batches": non_compliant,
            "summary": {
                "total_batches": len(batches),
                "compliant_count": len(compliant),
                "non_compliant_count": len(non_compliant),
                "no_coa_count": no_coa_count,
                "compliance_rate": len(compliant) / len(batches) * 100 if batches else 0,
                "tds_requirements_provided": bool(tds_requirements)
            }
        }
    
    def _check_single_batch(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Check compliance for a single batch.
        
        Args (in payload):
            batch_name: Batch name/lot number
            tds_requirements: TDS spec {param_name: {min, max}}
            
        Returns:
            Dict with compliant (bool), parameters dict
        """
        batch_name = payload.get('batch_name')
        tds_requirements = payload.get('tds_requirements', {})
        
        if not batch_name:
            return {"error": "batch_name is required"}
        
        coa_params = get_batch_coa_parameters(batch_name)
        
        if not coa_params:
            return {
                "batch_name": batch_name,
                "compliant": False,
                "reason": "No COA found",
                "parameters": {}
            }
        
        compliance = check_tds_compliance(coa_params, tds_requirements)
        
        return {
            "batch_name": batch_name,
            "compliant": compliance['all_pass'],
            "parameters": compliance['parameters'],
            "coa_source": coa_params.get(list(coa_params.keys())[0], {}).get('source', 'unknown') if coa_params else 'none'
        }
    
    def _compare_specs(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Compare actual batch parameters against TDS specifications.
        
        Args (in payload):
            batch_name: Batch name
            tds_requirements: TDS spec
            
        Returns:
            Detailed comparison with variance analysis
        """
        batch_name = payload.get('batch_name')
        tds_requirements = payload.get('tds_requirements', {})
        
        coa_params = get_batch_coa_parameters(batch_name)
        if not coa_params:
            return {"error": f"No COA found for {batch_name}"}
        
        comparison = []
        
        for param_name, spec in tds_requirements.items():
            actual = coa_params.get(param_name, {})
            actual_value = actual.get('value')
            spec_min = spec.get('min')
            spec_max = spec.get('max')
            
            # Calculate variance
            variance_from_min = None
            variance_from_max = None
            
            if actual_value is not None:
                if spec_min is not None:
                    variance_from_min = actual_value - spec_min
                if spec_max is not None:
                    variance_from_max = actual_value - spec_max
            
            # Determine status
            status = "N/A"
            if actual_value is not None:
                if spec_min is not None and actual_value < spec_min:
                    status = "BELOW_MIN"
                elif spec_max is not None and actual_value > spec_max:
                    status = "ABOVE_MAX"
                else:
                    status = "WITHIN_SPEC"
            elif actual_value is None:
                status = "NO_DATA"
            
            comparison.append({
                "parameter": param_name,
                "actual_value": actual_value,
                "spec_min": spec_min,
                "spec_max": spec_max,
                "status": status,
                "variance_from_min": variance_from_min,
                "variance_from_max": variance_from_max
            })
        
        return {
            "batch_name": batch_name,
            "comparison": comparison,
            "overall_status": "PASS" if all(c['status'] == 'WITHIN_SPEC' for c in comparison) else "FAIL"
        }
    
    def _get_compliance_report(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Generate a detailed compliance report.
        
        Args (in payload):
            batches: List of batches to report on
            tds_requirements: TDS spec
            format: Report format (summary, detailed, csv)
            
        Returns:
            Formatted compliance report
        """
        batches = payload.get('batches', [])
        tds_requirements = payload.get('tds_requirements', {})
        report_format = payload.get('format', 'summary')
        
        # Validate all batches
        validation = self._validate_compliance(
            {'batches': batches, 'tds_requirements': tds_requirements},
            message
        )
        
        if report_format == 'summary':
            return {
                "report_type": "summary",
                "generated_at": frappe.utils.now_datetime().isoformat(),
                "total_batches": validation['summary']['total_batches'],
                "compliant_count": validation['summary']['compliant_count'],
                "non_compliant_count": validation['summary']['non_compliant_count'],
                "compliance_rate": validation['summary']['compliance_rate'],
                "status": "PASS" if validation['passed'] else "FAIL"
            }
        
        elif report_format == 'detailed':
            return {
                "report_type": "detailed",
                "generated_at": frappe.utils.now_datetime().isoformat(),
                "tds_requirements": tds_requirements,
                "compliant_batches": validation['compliant_batches'],
                "non_compliant_batches": validation['non_compliant_batches'],
                "summary": validation['summary']
            }
        
        else:
            return validation


# Export for auto-discovery
AGENT_CLASS = TDSComplianceAgent
