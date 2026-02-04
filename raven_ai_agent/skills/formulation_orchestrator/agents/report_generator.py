"""
Report Generator Agent - Phase 6
================================

Generates comprehensive reports for formulation workflows.
"""

import frappe
from typing import Dict, List, Any, Optional
from datetime import datetime

from .base import BaseSubAgent
from ..messages import AgentMessage, WorkflowPhase, AgentChannel


class ReportGenerator(BaseSubAgent):
    """
    Report Generator Agent (Phase 6 of workflow).
    
    Responsibilities:
    - Generate workflow summary reports
    - Create compliance reports
    - Format output for different channels (Raven, PDF, etc.)
    - Provide actionable insights
    """
    
    name = "report_generator"
    description = "Report generation and formatting"
    emoji = "📊"
    phase = WorkflowPhase.REPORT_GENERATION
    
    def process(self, action: str, payload: Dict, message: AgentMessage) -> Optional[Dict]:
        """Route to specific action handler."""
        actions = {
            "generate_report": self._generate_report,
            "summary_report": self._summary_report,
            "compliance_report": self._compliance_report,
            "cost_report": self._cost_report,
            "format_for_raven": self._format_for_raven,
            "production_order_report": self._production_order_report,
            "format_as_ascii": self._format_as_ascii,
            "save_to_erpnext": self._save_to_erpnext,
            "email_report": self._email_report,
        }
        
        handler = actions.get(action)
        if handler:
            return handler(payload, message)
        return None
    
    def _generate_report(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Generate a comprehensive workflow report.
        
        Args (in payload):
            workflow_state: Complete workflow state
            report_type: Type of report (full, summary, compliance, cost)
            
        Returns:
            Dict with formatted report
        """
        workflow_state = payload.get('workflow_state', {})
        report_type = payload.get('report_type', 'full')
        
        self._log(f"Generating {report_type} report")
        self.send_status("generating", {"report_type": report_type})
        
        request = workflow_state.get('request', {})
        phases = workflow_state.get('phases', {})
        
        # Build report sections
        report = {
            "generated_at": datetime.now().isoformat(),
            "workflow_id": workflow_state.get('workflow_id'),
            "report_type": report_type,
            "request_summary": self._format_request_summary(request),
        }
        
        if report_type in ['full', 'summary']:
            report["batch_selection"] = self._format_batch_selection(
                phases.get('batch_selection', {})
            )
        
        if report_type in ['full', 'compliance']:
            report["compliance"] = self._format_compliance(
                phases.get('compliance', {})
            )
        
        if report_type in ['full', 'cost']:
            report["costs"] = self._format_costs(
                phases.get('costs', {})
            )
        
        if report_type == 'full':
            report["optimization"] = self._format_optimization(
                phases.get('optimization', {})
            )
            report["recommendations"] = self._generate_recommendations(phases)
        
        # Generate text summary
        report["text_summary"] = self._generate_text_summary(report)
        
        self.send_status("completed", {"report_type": report_type})
        
        return report
    
    def _summary_report(self, payload: Dict, message: AgentMessage) -> Dict:
        """Generate a quick summary report."""
        payload['report_type'] = 'summary'
        return self._generate_report(payload, message)
    
    def _compliance_report(self, payload: Dict, message: AgentMessage) -> Dict:
        """Generate a compliance-focused report."""
        payload['report_type'] = 'compliance'
        return self._generate_report(payload, message)
    
    def _cost_report(self, payload: Dict, message: AgentMessage) -> Dict:
        """Generate a cost-focused report."""
        payload['report_type'] = 'cost'
        return self._generate_report(payload, message)
    
    def _format_for_raven(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Format report for Raven channel.
        
        Args (in payload):
            report: Report dictionary
            channel: Target channel name
            
        Returns:
            Dict with Raven-formatted message
        """
        report = payload.get('report', {})
        
        # Create Raven-friendly markdown
        markdown = self._report_to_markdown(report)
        
        return {
            "format": "raven",
            "markdown": markdown,
            "channel_message": markdown
        }
    
    def _production_order_report(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Generate a production order report with material requirements.
        
        Args (in payload):
            workflow_state: Complete workflow state
            order_number: Production order number
            
        Returns:
            Dict with production order details and material requirements
        """
        workflow_state = payload.get('workflow_state', {})
        order_number = payload.get('order_number', 'PO-DRAFT')
        
        self._log(f"Generating production order report for {order_number}")
        self.send_status("generating", {"order_number": order_number})
        
        request = workflow_state.get('request', {})
        phases = workflow_state.get('phases', {})
        batch_selection = phases.get('batch_selection', {})
        costs = phases.get('costs', {})
        
        # Build production order structure
        production_order = {
            "order_number": order_number,
            "generated_at": datetime.now().isoformat(),
            "product": {
                "item_code": request.get('item_code'),
                "quantity": request.get('quantity_required'),
                "warehouse": request.get('warehouse'),
                "production_date": request.get('production_date'),
            },
            "materials": [],
            "costs": {
                "total": costs.get('total_cost', 0),
                "per_unit": costs.get('cost_per_unit', 0),
                "currency": costs.get('currency', 'MXN')
            },
            "status": "draft"
        }
        
        # Add selected batches as material requirements
        for batch in batch_selection.get('selected_batches', []):
            production_order["materials"].append({
                "batch_name": batch.get('batch_name'),
                "item_code": batch.get('item_code'),
                "quantity": batch.get('qty_available', batch.get('qty')),
                "warehouse": batch.get('warehouse'),
                "fefo_key": batch.get('fefo_key'),
                "year": batch.get('year')
            })
        
        self.send_status("completed", {"order_number": order_number})
        
        return production_order
    
    def _format_as_ascii(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Format report as ASCII text for terminal display or plain text files.
        
        Args (in payload):
            report: Report dictionary to format
            report_type: Type of report (production_order, cost, compliance)
            
        Returns:
            Dict with ASCII formatted text
        """
        report = payload.get('report', {})
        report_type = payload.get('report_type', 'general')
        
        self._log(f"Formatting {report_type} report as ASCII")
        
        if report_type == 'production_order':
            ascii_text = self._format_production_order_ascii(report)
        elif report_type == 'cost':
            ascii_text = self._format_cost_ascii(report)
        elif report_type == 'compliance':
            ascii_text = self._format_compliance_ascii(report)
        else:
            # Use general text summary
            ascii_text = self._generate_text_summary(report)
        
        return {
            "format": "ascii",
            "text": ascii_text
        }
    
    def _save_to_erpnext(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Save report or production order to ERPNext.
        
        Args (in payload):
            report: Report or production order dictionary
            doctype: ERPNext doctype (e.g., 'Production Order', 'Work Order')
            
        Returns:
            Dict with save status and document name
        """
        report = payload.get('report', {})
        doctype = payload.get('doctype', 'Production Order')
        
        self._log(f"Saving to ERPNext: {doctype}")
        self.send_status("saving", {"doctype": doctype})
        
        try:
            # Create ERPNext document
            doc = frappe.get_doc({
                "doctype": doctype,
                "title": report.get('order_number', 'Draft Report'),
                "production_item": report.get('product', {}).get('item_code'),
                "qty": report.get('product', {}).get('quantity'),
                "wip_warehouse": report.get('product', {}).get('warehouse'),
                "planned_start_date": report.get('product', {}).get('production_date'),
                "status": "Draft"
            })
            
            # Add material requirements as child table entries
            for material in report.get('materials', []):
                doc.append('required_items', {
                    'item_code': material.get('item_code'),
                    'required_qty': material.get('quantity'),
                    'source_warehouse': material.get('warehouse'),
                    'batch_no': material.get('batch_name')
                })
            
            doc.insert()
            
            self.send_status("completed", {
                "doctype": doctype,
                "name": doc.name
            })
            
            return {
                "success": True,
                "doctype": doctype,
                "name": doc.name,
                "message": f"{doctype} created successfully"
            }
            
        except Exception as e:
            self._log(f"Failed to save to ERPNext: {str(e)}", level="error")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to create {doctype}"
            }
    
    def _email_report(self, payload: Dict, message: AgentMessage) -> Dict:
        """
        Email report to specified recipients.
        
        Args (in payload):
            report: Report dictionary
            recipients: List of email addresses
            subject: Email subject line
            format: Report format (markdown, ascii, html)
            
        Returns:
            Dict with email status
        """
        report = payload.get('report', {})
        recipients = payload.get('recipients', [])
        subject = payload.get('subject', 'Formulation Workflow Report')
        format_type = payload.get('format', 'markdown')
        
        if not recipients:
            return {
                "success": False,
                "error": "No recipients specified"
            }
        
        self._log(f"Emailing report to {len(recipients)} recipient(s)")
        self.send_status("sending", {"recipients": len(recipients)})
        
        try:
            # Format report content
            if format_type == 'ascii':
                content = self._generate_text_summary(report)
                content_type = 'text/plain'
            else:  # markdown or html
                content = self._report_to_markdown(report)
                content_type = 'text/html' if format_type == 'html' else 'text/plain'
            
            # Send email using Frappe's email API
            frappe.sendmail(
                recipients=recipients,
                subject=subject,
                message=content,
                now=True
            )
            
            self.send_status("completed", {"recipients": len(recipients)})
            
            return {
                "success": True,
                "recipients": recipients,
                "message": f"Report emailed to {len(recipients)} recipient(s)"
            }
            
        except Exception as e:
            self._log(f"Failed to email report: {str(e)}", level="error")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to send email"
            }
    
    def _format_request_summary(self, request: Dict) -> Dict:
        """Format the initial request summary."""
        return {
            "item_code": request.get('item_code'),
            "quantity_required": request.get('quantity_required'),
            "warehouse": request.get('warehouse'),
            "production_date": request.get('production_date'),
            "customer": request.get('customer'),
            "sales_order": request.get('sales_order')
        }
    
    def _format_batch_selection(self, batch_selection: Dict) -> Dict:
        """Format batch selection results."""
        selected = batch_selection.get('selected_batches', [])
        
        return {
            "total_batches": len(selected),
            "total_qty": batch_selection.get('total_qty', 0),
            "coverage_percent": batch_selection.get('coverage_percent', 0),
            "batches": [
                {
                    "batch_name": b.get('batch_name'),
                    "qty": b.get('qty_available', b.get('qty')),
                    "fefo_key": b.get('fefo_key'),
                    "year": b.get('year')
                }
                for b in selected
            ]
        }
    
    def _format_compliance(self, compliance: Dict) -> Dict:
        """Format compliance results."""
        return {
            "passed": compliance.get('passed', False),
            "compliant_count": len(compliance.get('compliant_batches', [])),
            "non_compliant_count": len(compliance.get('non_compliant_batches', [])),
            "compliance_rate": compliance.get('summary', {}).get('compliance_rate', 0),
            "failing_batches": [
                {
                    "batch_name": b.get('batch_name'),
                    "failing_parameters": b.get('failing_parameters', [])
                }
                for b in compliance.get('non_compliant_batches', [])
            ]
        }
    
    def _format_costs(self, costs: Dict) -> Dict:
        """Format cost results."""
        return {
            "total_cost": costs.get('total_cost', 0),
            "raw_material_cost": costs.get('raw_material_cost', 0),
            "overhead_cost": costs.get('overhead_cost', 0),
            "cost_per_unit": costs.get('cost_per_unit', 0),
            "currency": costs.get('currency', 'MXN')
        }
    
    def _format_optimization(self, optimization: Dict) -> Dict:
        """Format optimization results."""
        return {
            "recommendations_count": len(optimization.get('recommendations', [])),
            "optimization_applied": optimization.get('optimization_applied', False),
            "recommendations": optimization.get('recommendations', [])
        }
    
    def _generate_recommendations(self, phases: Dict) -> List[str]:
        """Generate actionable recommendations based on workflow results."""
        recommendations = []
        
        compliance = phases.get('compliance', {})
        costs = phases.get('costs', {})
        optimization = phases.get('optimization', {})
        
        # Compliance recommendations
        if not compliance.get('passed', True):
            non_compliant = compliance.get('non_compliant_batches', [])
            recommendations.append(
                f"⚠️ {len(non_compliant)} batch(es) failed TDS compliance. "
                "Consider using suggested alternatives."
            )
        
        # Cost recommendations
        if costs:
            cost_per_unit = costs.get('cost_per_unit', 0)
            # Could add threshold-based recommendations here
            
        # Optimization recommendations
        if optimization.get('recommendations'):
            for rec in optimization['recommendations']:
                if rec.get('type') == 'replace_batch':
                    recommendations.append(
                        f"💡 Replace batch {rec.get('original_batch')} with "
                        f"one of {len(rec.get('alternatives', []))} compliant alternatives"
                    )
        
        if not recommendations:
            recommendations.append("✅ All criteria met. Proceed with production.")
        
        return recommendations
    
    def _generate_text_summary(self, report: Dict) -> str:
        """Generate a human-readable text summary."""
        lines = []
        
        lines.append("=" * 50)
        lines.append("FORMULATION WORKFLOW REPORT")
        lines.append(f"Generated: {report.get('generated_at', 'Unknown')}")
        lines.append("=" * 50)
        
        # Request summary
        request = report.get('request_summary', {})
        if request:
            lines.append("\n📋 REQUEST:")
            lines.append(f"  Item: {request.get('item_code')}")
            lines.append(f"  Quantity: {request.get('quantity_required')}")
            lines.append(f"  Warehouse: {request.get('warehouse')}")
        
        # Batch selection
        batch_sel = report.get('batch_selection', {})
        if batch_sel:
            lines.append("\n📦 BATCH SELECTION:")
            lines.append(f"  Batches Selected: {batch_sel.get('total_batches')}")
            lines.append(f"  Total Quantity: {batch_sel.get('total_qty')}")
            lines.append(f"  Coverage: {batch_sel.get('coverage_percent', 0):.1f}%")
        
        # Compliance
        compliance = report.get('compliance', {})
        if compliance:
            status = "✅ PASSED" if compliance.get('passed') else "❌ FAILED"
            lines.append(f"\n✅ COMPLIANCE: {status}")
            lines.append(f"  Compliant: {compliance.get('compliant_count')}")
            lines.append(f"  Non-Compliant: {compliance.get('non_compliant_count')}")
        
        # Costs
        costs = report.get('costs', {})
        if costs:
            lines.append("\n💰 COSTS:")
            lines.append(f"  Total: {costs.get('currency', 'MXN')} {costs.get('total_cost', 0):,.2f}")
            lines.append(f"  Per Unit: {costs.get('currency', 'MXN')} {costs.get('cost_per_unit', 0):,.2f}")
        
        # Recommendations
        recommendations = report.get('recommendations', [])
        if recommendations:
            lines.append("\n💡 RECOMMENDATIONS:")
            for rec in recommendations:
                lines.append(f"  • {rec}")
        
        lines.append("\n" + "=" * 50)
        
        return "\n".join(lines)
    
    def _report_to_markdown(self, report: Dict) -> str:
        """Convert report to Markdown format for Raven."""
        lines = []
        
        lines.append("## 📊 Formulation Workflow Report")
        lines.append(f"*Generated: {report.get('generated_at', 'Unknown')}*")
        lines.append("")
        
        # Request summary
        request = report.get('request_summary', {})
        if request:
            lines.append("### 📋 Request")
            lines.append(f"| Field | Value |")
            lines.append("|-------|-------|")
            lines.append(f"| Item | `{request.get('item_code')}` |")
            lines.append(f"| Quantity | {request.get('quantity_required')} |")
            lines.append(f"| Warehouse | {request.get('warehouse')} |")
            lines.append("")
        
        # Batch selection
        batch_sel = report.get('batch_selection', {})
        if batch_sel:
            lines.append("### 📦 Batch Selection")
            lines.append(f"- **Batches:** {batch_sel.get('total_batches')}")
            lines.append(f"- **Total Qty:** {batch_sel.get('total_qty')}")
            lines.append(f"- **Coverage:** {batch_sel.get('coverage_percent', 0):.1f}%")
            lines.append("")
        
        # Compliance
        compliance = report.get('compliance', {})
        if compliance:
            status_icon = "✅" if compliance.get('passed') else "❌"
            lines.append(f"### {status_icon} Compliance")
            lines.append(f"- Compliant: {compliance.get('compliant_count')}")
            lines.append(f"- Non-Compliant: {compliance.get('non_compliant_count')}")
            lines.append("")
        
        # Costs
        costs = report.get('costs', {})
        if costs:
            currency = costs.get('currency', 'MXN')
            lines.append("### 💰 Costs")
            lines.append(f"- **Total:** {currency} {costs.get('total_cost', 0):,.2f}")
            lines.append(f"- **Per Unit:** {currency} {costs.get('cost_per_unit', 0):,.2f}")
            lines.append("")
        
        # Recommendations
        recommendations = report.get('recommendations', [])
        if recommendations:
            lines.append("### 💡 Recommendations")
            for rec in recommendations:
                lines.append(f"- {rec}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_production_order_ascii(self, production_order: Dict) -> str:
        """
        Format production order as ASCII text.
        
        Args:
            production_order: Production order dictionary
            
        Returns:
            ASCII formatted string
        """
        lines = []
        
        lines.append("=" * 60)
        lines.append("PRODUCTION ORDER")
        lines.append(f"Order Number: {production_order.get('order_number')}")
        lines.append(f"Generated: {production_order.get('generated_at')}")
        lines.append("=" * 60)
        
        # Product details
        product = production_order.get('product', {})
        lines.append("\nPRODUCT:")
        lines.append(f"  Item Code: {product.get('item_code')}")
        lines.append(f"  Quantity: {product.get('quantity')}")
        lines.append(f"  Warehouse: {product.get('warehouse')}")
        lines.append(f"  Production Date: {product.get('production_date')}")
        
        # Material requirements
        materials = production_order.get('materials', [])
        lines.append(f"\nMATERIAL REQUIREMENTS ({len(materials)} batches):")
        lines.append("-" * 60)
        for i, material in enumerate(materials, 1):
            lines.append(f"\n{i}. {material.get('batch_name')}")
            lines.append(f"   Item: {material.get('item_code')}")
            lines.append(f"   Qty: {material.get('quantity')}")
            lines.append(f"   Warehouse: {material.get('warehouse')}")
            lines.append(f"   FEFO Key: {material.get('fefo_key')}")
        
        # Costs
        costs = production_order.get('costs', {})
        lines.append("\nCOSTS:")
        lines.append(f"  Total: {costs.get('currency', 'MXN')} {costs.get('total', 0):,.2f}")
        lines.append(f"  Per Unit: {costs.get('currency', 'MXN')} {costs.get('per_unit', 0):,.2f}")
        
        lines.append("\n" + "=" * 60)
        lines.append(f"Status: {production_order.get('status', 'draft').upper()}")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def _format_cost_ascii(self, report: Dict) -> str:
        """
        Format cost report as ASCII text.
        
        Args:
            report: Cost report dictionary
            
        Returns:
            ASCII formatted string
        """
        lines = []
        costs = report.get('costs', {})
        request = report.get('request_summary', {})
        
        lines.append("=" * 50)
        lines.append("COST ANALYSIS REPORT")
        lines.append(f"Generated: {report.get('generated_at')}")
        lines.append("=" * 50)
        
        lines.append("\nITEM:")
        lines.append(f"  {request.get('item_code')} - Qty: {request.get('quantity_required')}")
        
        currency = costs.get('currency', 'MXN')
        lines.append("\nCOST BREAKDOWN:")
        lines.append(f"  Raw Materials: {currency} {costs.get('raw_material_cost', 0):,.2f}")
        lines.append(f"  Overhead: {currency} {costs.get('overhead_cost', 0):,.2f}")
        lines.append(f"  " + "-" * 40)
        lines.append(f"  TOTAL COST: {currency} {costs.get('total_cost', 0):,.2f}")
        lines.append(f"\n  Cost Per Unit: {currency} {costs.get('cost_per_unit', 0):,.2f}")
        
        lines.append("\n" + "=" * 50)
        
        return "\n".join(lines)
    
    def _format_compliance_ascii(self, report: Dict) -> str:
        """
        Format compliance report as ASCII text.
        
        Args:
            report: Compliance report dictionary
            
        Returns:
            ASCII formatted string
        """
        lines = []
        compliance = report.get('compliance', {})
        request = report.get('request_summary', {})
        
        lines.append("=" * 50)
        lines.append("COMPLIANCE REPORT")
        lines.append(f"Generated: {report.get('generated_at')}")
        lines.append("=" * 50)
        
        lines.append("\nITEM:")
        lines.append(f"  {request.get('item_code')}")
        
        status = "PASSED" if compliance.get('passed') else "FAILED"
        status_symbol = "[+]" if compliance.get('passed') else "[X]"
        
        lines.append(f"\nSTATUS: {status_symbol} {status}")
        lines.append(f"  Compliant Batches: {compliance.get('compliant_count', 0)}")
        lines.append(f"  Non-Compliant Batches: {compliance.get('non_compliant_count', 0)}")
        lines.append(f"  Compliance Rate: {compliance.get('compliance_rate', 0):.1f}%")
        
        # List failing batches
        failing = compliance.get('failing_batches', [])
        if failing:
            lines.append("\nFAILING BATCHES:")
            for batch in failing:
                lines.append(f"\n  - {batch.get('batch_name')}")
                for param in batch.get('failing_parameters', []):
                    lines.append(f"    * {param}")
        
        lines.append("\n" + "=" * 50)
        
        return "\n".join(lines)


# Export for auto-discovery
AGENT_CLASS = ReportGenerator
