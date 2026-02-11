"""
Migration Fixer Skill
FoxPro -> ERPNext Migration Validation and Repair

Flow: FoxPro JSON -> Quotation -> Sales Order (skipping Lead/Opportunity)

Folio Ranges:
- 2024: 00752 - 00980
- 2025: 00980 - 01160
"""

import frappe
import json
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path


class MigrationFixer:
    """
    Migration validation and repair for FoxPro -> ERPNext
    
    Usage:
        fixer = MigrationFixer()
        issues = fixer.scan_range("00752", "00980", year=2024)
        fixer.fix_quotation("00752", dry_run=True)
    """
    
    FOLIO_RANGES = {
        2024: {"start": "00752", "end": "00980"},
        2025: {"start": "00980", "end": "01160"}
    }
    
    def __init__(self, json_source_path: str = None):
        """
        Initialize the migration fixer
        
        Args:
            json_source_path: Path to directory containing FoxPro JSON extracts
        """
        self.json_path = json_source_path or frappe.conf.get("foxpro_json_path", "/home/frappe/foxpro_data")
        self.fix_log = []
        
    # ==========================================
    # JSON Source Methods
    # ==========================================
    
    def load_foxpro_json(self, invoice_folio: str) -> Optional[Dict]:
        """Load FoxPro JSON data for a specific invoice folio"""
        patterns = [
            f"{invoice_folio}.json",
            f"invoice_{invoice_folio}.json",
            f"folio_{invoice_folio}.json",
        ]
        
        for pattern in patterns:
            filepath = os.path.join(self.json_path, pattern)
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
        
        # Try searching in subdirectories
        for root, dirs, files in os.walk(self.json_path):
            for pattern in patterns:
                if pattern in files:
                    with open(os.path.join(root, pattern), 'r', encoding='utf-8') as f:
                        return json.load(f)
        
        return None
    
    def list_available_folios(self, year: int = None) -> List[str]:
        """List all available FoxPro JSON folios"""
        folios = []
        
        for root, dirs, files in os.walk(self.json_path):
            for f in files:
                if f.endswith('.json'):
                    # Extract folio from filename
                    folio = f.replace('.json', '').replace('invoice_', '').replace('folio_', '')
                    if folio.isdigit() or (len(folio) == 5 and folio[0:2].isdigit()):
                        folios.append(folio)
        
        folios.sort()
        
        if year:
            range_info = self.FOLIO_RANGES.get(year, {})
            start = range_info.get("start", "00000")
            end = range_info.get("end", "99999")
            folios = [f for f in folios if start <= f <= end]
        
        return folios
    
    # ==========================================
    # ERPNext Query Methods
    # ==========================================
    
    def get_quotation_by_folio(self, invoice_folio: str) -> Optional[Dict]:
        """Find Quotation linked to invoice folio"""
        # Try custom field first
        quotations = frappe.get_all(
            "Quotation",
            filters={"custom_invoice_folio": invoice_folio},
            fields=["name", "customer", "transaction_date", "grand_total", "status", 
                   "custom_invoice_folio", "custom_lote_real"]
        )
        
        if quotations:
            return frappe.get_doc("Quotation", quotations[0].name)
        
        # Try searching in title/remarks
        quotations = frappe.get_all(
            "Quotation",
            filters=[
                ["Quotation", "title", "like", f"%{invoice_folio}%"]
            ],
            fields=["name"]
        )
        
        if quotations:
            return frappe.get_doc("Quotation", quotations[0].name)
        
        return None
    
    def get_sales_order_by_quotation(self, quotation_name: str) -> Optional[Dict]:
        """Find Sales Order linked to Quotation"""
        orders = frappe.get_all(
            "Sales Order",
            filters={"custom_quotation_reference": quotation_name},
            fields=["name", "customer", "transaction_date", "grand_total", "status"]
        )
        
        if orders:
            return frappe.get_doc("Sales Order", orders[0].name)
        
        # Try via Sales Order Item
        links = frappe.get_all(
            "Sales Order Item",
            filters={"prevdoc_docname": quotation_name},
            fields=["parent"]
        )
        
        if links:
            return frappe.get_doc("Sales Order", links[0].parent)
        
        return None
    
    def get_quotations_in_range(self, start_folio: str, end_folio: str) -> List[Dict]:
        """Get all quotations in folio range"""
        return frappe.get_all(
            "Quotation",
            filters=[
                ["custom_invoice_folio", ">=", start_folio],
                ["custom_invoice_folio", "<=", end_folio]
            ],
            fields=["name", "customer", "transaction_date", "grand_total", "status",
                   "custom_invoice_folio", "custom_lote_real"],
            order_by="custom_invoice_folio"
        )
    
    # ==========================================
    # Validation Methods
    # ==========================================
    
    def validate_quotation(self, invoice_folio: str) -> Dict:
        """
        Validate a single quotation against FoxPro source
        
        Returns:
            {
                "folio": str,
                "status": "ok" | "warning" | "error" | "missing",
                "issues": List[str],
                "foxpro_data": Dict,
                "erpnext_data": Dict
            }
        """
        result = {
            "folio": invoice_folio,
            "status": "ok",
            "issues": [],
            "foxpro_data": None,
            "erpnext_data": None
        }
        
        # Load source data
        foxpro = self.load_foxpro_json(invoice_folio)
        if not foxpro:
            result["status"] = "warning"
            result["issues"].append("FoxPro JSON not found")
        else:
            result["foxpro_data"] = foxpro
        
        # Get ERPNext quotation
        quotation = self.get_quotation_by_folio(invoice_folio)
        if not quotation:
            result["status"] = "error"
            result["issues"].append("Quotation not found in ERPNext")
            return result
        
        result["erpnext_data"] = {
            "name": quotation.name,
            "customer": quotation.customer,
            "date": str(quotation.transaction_date),
            "total": float(quotation.grand_total),
            "items": [{"item": i.item_code, "qty": i.qty, "rate": i.rate} 
                     for i in quotation.items]
        }
        
        # Compare if we have source data
        if foxpro:
            issues = self._compare_data(foxpro, quotation)
            if issues:
                result["status"] = "warning" if len(issues) < 3 else "error"
                result["issues"].extend(issues)
        
        return result
    
    def _compare_data(self, foxpro: Dict, quotation) -> List[str]:
        """Compare FoxPro data with ERPNext quotation"""
        issues = []
        
        # Customer comparison
        foxpro_customer = foxpro.get("customer") or foxpro.get("cliente") or foxpro.get("client_name")
        if foxpro_customer and quotation.customer:
            if foxpro_customer.lower().strip() not in quotation.customer.lower():
                issues.append(f"Customer mismatch: FoxPro='{foxpro_customer}' vs ERPNext='{quotation.customer}'")
        
        # Total comparison (with 1% tolerance)
        foxpro_total = float(foxpro.get("total") or foxpro.get("grand_total") or foxpro.get("importe") or 0)
        if foxpro_total > 0:
            erpnext_total = float(quotation.grand_total)
            diff_pct = abs(foxpro_total - erpnext_total) / foxpro_total * 100
            if diff_pct > 1:
                issues.append(f"Total mismatch ({diff_pct:.1f}%): FoxPro=${foxpro_total:,.2f} vs ERPNext=${erpnext_total:,.2f}")
        
        # Date comparison
        foxpro_date = foxpro.get("date") or foxpro.get("fecha")
        if foxpro_date:
            try:
                fp_date = datetime.strptime(str(foxpro_date)[:10], "%Y-%m-%d").date()
                if fp_date != quotation.transaction_date:
                    issues.append(f"Date mismatch: FoxPro={fp_date} vs ERPNext={quotation.transaction_date}")
            except:
                pass
        
        # Item count comparison
        foxpro_items = foxpro.get("items") or foxpro.get("lineas") or foxpro.get("details") or []
        if len(foxpro_items) != len(quotation.items):
            issues.append(f"Item count mismatch: FoxPro={len(foxpro_items)} vs ERPNext={len(quotation.items)}")
        
        # Lote_real check
        lote_real = foxpro.get("lote_real") or foxpro.get("lote")
        if lote_real and hasattr(quotation, 'custom_lote_real'):
            if str(lote_real) != str(quotation.custom_lote_real or ''):
                issues.append(f"Lote_real mismatch: FoxPro='{lote_real}' vs ERPNext='{quotation.custom_lote_real}'")
        
        return issues
    
    def scan_range(self, start_folio: str, end_folio: str, year: int = None) -> Dict:
        """
        Scan a range of folios and report issues
        
        Returns:
            {
                "scanned": int,
                "ok": int,
                "warnings": int,
                "errors": int,
                "missing": int,
                "details": List[Dict]
            }
        """
        if year and year in self.FOLIO_RANGES:
            range_info = self.FOLIO_RANGES[year]
            start_folio = start_folio or range_info["start"]
            end_folio = end_folio or range_info["end"]
        
        results = {
            "scanned": 0,
            "ok": 0,
            "warnings": 0,
            "errors": 0,
            "missing": 0,
            "details": []
        }
        
        # Generate folio range
        start_num = int(start_folio)
        end_num = int(end_folio)
        
        for num in range(start_num, end_num + 1):
            folio = str(num).zfill(5)
            
            validation = self.validate_quotation(folio)
            results["scanned"] += 1
            results[validation["status"]] = results.get(validation["status"], 0) + 1
            
            if validation["status"] != "ok":
                results["details"].append(validation)
        
        return results
    
    # ==========================================
    # Fix Methods
    # ==========================================
    
    def fix_quotation(self, invoice_folio: str, dry_run: bool = True) -> Dict:
        """
        Apply fixes to a quotation based on FoxPro source
        
        Args:
            invoice_folio: The folio to fix
            dry_run: If True, only preview changes without applying
            
        Returns:
            {
                "folio": str,
                "changes": List[Dict],
                "applied": bool,
                "error": str (if any)
            }
        """
        result = {
            "folio": invoice_folio,
            "changes": [],
            "applied": False,
            "error": None
        }
        
        # Load source data
        foxpro = self.load_foxpro_json(invoice_folio)
        if not foxpro:
            result["error"] = "FoxPro JSON not found - cannot determine correct values"
            return result
        
        # Get quotation
        quotation = self.get_quotation_by_folio(invoice_folio)
        if not quotation:
            result["error"] = "Quotation not found in ERPNext"
            return result
        
        # Determine fixes needed
        changes = []
        
        # Fix lote_real
        lote_real = foxpro.get("lote_real") or foxpro.get("lote")
        if lote_real and str(lote_real) != str(quotation.custom_lote_real or ''):
            changes.append({
                "field": "custom_lote_real",
                "old": quotation.custom_lote_real,
                "new": str(lote_real),
                "type": "update"
            })
        
        # Fix customer if clearly wrong
        foxpro_customer = foxpro.get("customer") or foxpro.get("cliente")
        if foxpro_customer:
            # Check if customer exists in ERPNext
            customer_match = frappe.db.exists("Customer", {"customer_name": ["like", f"%{foxpro_customer}%"]})
            if customer_match and customer_match != quotation.customer:
                changes.append({
                    "field": "customer",
                    "old": quotation.customer,
                    "new": customer_match,
                    "type": "update"
                })
        
        # Fix date if different
        foxpro_date = foxpro.get("date") or foxpro.get("fecha")
        if foxpro_date:
            try:
                fp_date = datetime.strptime(str(foxpro_date)[:10], "%Y-%m-%d").date()
                if fp_date != quotation.transaction_date:
                    changes.append({
                        "field": "transaction_date",
                        "old": str(quotation.transaction_date),
                        "new": str(fp_date),
                        "type": "update"
                    })
            except:
                pass
        
        result["changes"] = changes
        
        # Apply if not dry run
        if not dry_run and changes:
            try:
                doc = frappe.get_doc("Quotation", quotation.name)
                
                for change in changes:
                    if change["type"] == "update":
                        setattr(doc, change["field"], change["new"])
                
                doc.flags.ignore_validate = True
                doc.flags.ignore_permissions = True
                doc.save()
                
                result["applied"] = True
                
                # Log the fix
                self.fix_log.append({
                    "timestamp": datetime.now().isoformat(),
                    "folio": invoice_folio,
                    "quotation": quotation.name,
                    "changes": changes
                })
                
            except Exception as e:
                result["error"] = str(e)
        
        return result
    
    def bulk_fix(self, start_folio: str, end_folio: str, dry_run: bool = True) -> Dict:
        """
        Apply fixes to a range of quotations
        
        Returns summary of all fixes applied
        """
        results = {
            "processed": 0,
            "fixed": 0,
            "skipped": 0,
            "errors": 0,
            "details": []
        }
        
        start_num = int(start_folio)
        end_num = int(end_folio)
        
        for num in range(start_num, end_num + 1):
            folio = str(num).zfill(5)
            
            fix_result = self.fix_quotation(folio, dry_run=dry_run)
            results["processed"] += 1
            
            if fix_result.get("error"):
                results["errors"] += 1
            elif fix_result.get("changes"):
                results["fixed"] += 1
                results["details"].append(fix_result)
            else:
                results["skipped"] += 1
        
        return results
    
    # ==========================================
    # Reporting Methods
    # ==========================================
    
    def generate_report(self, year: int = None) -> str:
        """Generate a comprehensive migration status report"""
        ranges = [year] if year else [2024, 2025]
        
        report = []
        report.append("# Migration Status Report")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        report.append("")
        
        for yr in ranges:
            range_info = self.FOLIO_RANGES.get(yr, {})
            if not range_info:
                continue
            
            report.append(f"## Year {yr}")
            report.append(f"Folio Range: {range_info['start']} - {range_info['end']}")
            report.append("")
            
            scan = self.scan_range(range_info['start'], range_info['end'])
            
            report.append(f"| Metric | Count |")
            report.append(f"|--------|-------|")
            report.append(f"| Scanned | {scan['scanned']} |")
            report.append(f"| OK | {scan['ok']} |")
            report.append(f"| Warnings | {scan['warnings']} |")
            report.append(f"| Errors | {scan['errors']} |")
            report.append(f"| Missing | {scan['missing']} |")
            report.append("")
            
            if scan['details']:
                report.append("### Issues Found")
                for detail in scan['details'][:20]:  # Limit to first 20
                    report.append(f"- **{detail['folio']}** ({detail['status']}): {', '.join(detail['issues'][:3])}")
                
                if len(scan['details']) > 20:
                    report.append(f"  ... and {len(scan['details']) - 20} more")
            
            report.append("")
        
        return "\n".join(report)
    
    def get_fix_log(self) -> List[Dict]:
        """Return the fix log for this session"""
        return self.fix_log


# Convenience functions for Raven chat commands

def scan_migration(year: int = None, start: str = None, end: str = None) -> str:
    """
    Scan migration status
    
    Usage in Raven:
        "scan migration 2024"
        "scan migration from 00800 to 00850"
    """
    fixer = MigrationFixer()
    
    if year:
        range_info = MigrationFixer.FOLIO_RANGES.get(year, {})
        start = start or range_info.get("start")
        end = end or range_info.get("end")
    
    if not start or not end:
        return "Please specify year (2024/2025) or folio range (start, end)"
    
    results = fixer.scan_range(start, end)
    
    summary = f"""
📊 **Migration Scan Results**
- Scanned: {results['scanned']}
- ✅ OK: {results['ok']}
- ⚠️ Warnings: {results['warnings']}  
- ❌ Errors: {results['errors']}
- 📭 Missing: {results['missing']}
"""
    
    if results['details']:
        summary += "\n**Top Issues:**\n"
        for d in results['details'][:5]:
            summary += f"- {d['folio']}: {d['issues'][0] if d['issues'] else 'Unknown'}\n"
    
    return summary


def fix_folio(invoice_folio: str, confirm: bool = False) -> str:
    """
    Fix a specific folio
    
    Usage in Raven:
        "fix folio 00752"
        "fix folio 00752 confirm"
    """
    fixer = MigrationFixer()
    result = fixer.fix_quotation(invoice_folio, dry_run=not confirm)
    
    if result.get("error"):
        return f"❌ Error: {result['error']}"
    
    if not result.get("changes"):
        return f"✅ Folio {invoice_folio}: No fixes needed"
    
    changes_text = "\n".join([
        f"  - {c['field']}: '{c['old']}' → '{c['new']}'"
        for c in result['changes']
    ])
    
    if result.get("applied"):
        return f"✅ Fixed folio {invoice_folio}:\n{changes_text}"
    else:
        return f"🔍 Preview for folio {invoice_folio}:\n{changes_text}\n\n*Say 'fix folio {invoice_folio} confirm' to apply*"
