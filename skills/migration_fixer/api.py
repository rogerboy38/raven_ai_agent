"""
Migration Fixer API Endpoints
For use via Frappe API and Raven integration
"""

import frappe
import json
from typing import Dict, List, Optional

from raven_ai_agent.skills.migration_fixer.fixer import MigrationFixer, scan_migration, fix_folio


@frappe.whitelist()
def scan_folios(year: int = None, start_folio: str = None, end_folio: str = None) -> Dict:
    """
    API: Scan migration status for a folio range
    
    Args:
        year: 2024 or 2025 (uses predefined ranges)
        start_folio: Starting folio (e.g., "00752")
        end_folio: Ending folio (e.g., "00980")
    
    Returns:
        Scan results with counts and issue details
    """
    fixer = MigrationFixer()
    
    if year:
        year = int(year)
        range_info = MigrationFixer.FOLIO_RANGES.get(year, {})
        start_folio = start_folio or range_info.get("start")
        end_folio = end_folio or range_info.get("end")
    
    if not start_folio or not end_folio:
        return {"error": "Please specify year or folio range"}
    
    return fixer.scan_range(start_folio, end_folio)


@frappe.whitelist()
def validate_folio(invoice_folio: str) -> Dict:
    """
    API: Validate a single folio
    
    Args:
        invoice_folio: The invoice folio to validate (e.g., "00752")
    
    Returns:
        Validation result with issues if any
    """
    fixer = MigrationFixer()
    return fixer.validate_quotation(invoice_folio)


@frappe.whitelist()
def preview_fix(invoice_folio: str) -> Dict:
    """
    API: Preview fixes for a folio (dry run)
    
    Args:
        invoice_folio: The invoice folio to check
    
    Returns:
        Proposed changes without applying them
    """
    fixer = MigrationFixer()
    return fixer.fix_quotation(invoice_folio, dry_run=True)


@frappe.whitelist()
def apply_fix(invoice_folio: str) -> Dict:
    """
    API: Apply fixes to a folio
    
    Args:
        invoice_folio: The invoice folio to fix
    
    Returns:
        Fix result with applied changes
    """
    fixer = MigrationFixer()
    return fixer.fix_quotation(invoice_folio, dry_run=False)


@frappe.whitelist()
def bulk_preview(start_folio: str, end_folio: str) -> Dict:
    """
    API: Preview fixes for a range of folios
    """
    fixer = MigrationFixer()
    return fixer.bulk_fix(start_folio, end_folio, dry_run=True)


@frappe.whitelist()
def bulk_apply(start_folio: str, end_folio: str) -> Dict:
    """
    API: Apply fixes to a range of folios
    
    ⚠️ Use with caution - this modifies data
    """
    fixer = MigrationFixer()
    return fixer.bulk_fix(start_folio, end_folio, dry_run=False)


@frappe.whitelist()
def get_migration_report(year: int = None) -> str:
    """
    API: Generate full migration status report
    
    Args:
        year: Optional - filter to specific year
    
    Returns:
        Markdown formatted report
    """
    fixer = MigrationFixer()
    return fixer.generate_report(year=int(year) if year else None)


@frappe.whitelist()
def get_foxpro_data(invoice_folio: str) -> Dict:
    """
    API: Get raw FoxPro JSON data for a folio
    """
    fixer = MigrationFixer()
    data = fixer.load_foxpro_json(invoice_folio)
    return data if data else {"error": "FoxPro JSON not found"}


@frappe.whitelist()
def compare_folio(invoice_folio: str) -> Dict:
    """
    API: Side-by-side comparison of FoxPro vs ERPNext data
    """
    fixer = MigrationFixer()
    
    foxpro = fixer.load_foxpro_json(invoice_folio)
    quotation = fixer.get_quotation_by_folio(invoice_folio)
    
    result = {
        "folio": invoice_folio,
        "foxpro": None,
        "erpnext": None,
        "differences": []
    }
    
    if foxpro:
        result["foxpro"] = {
            "customer": foxpro.get("customer") or foxpro.get("cliente"),
            "date": foxpro.get("date") or foxpro.get("fecha"),
            "total": foxpro.get("total") or foxpro.get("grand_total") or foxpro.get("importe"),
            "lote_real": foxpro.get("lote_real") or foxpro.get("lote"),
            "items_count": len(foxpro.get("items") or foxpro.get("lineas") or [])
        }
    
    if quotation:
        result["erpnext"] = {
            "name": quotation.name,
            "customer": quotation.customer,
            "date": str(quotation.transaction_date),
            "total": float(quotation.grand_total),
            "lote_real": getattr(quotation, 'custom_lote_real', None),
            "items_count": len(quotation.items)
        }
    
    # Calculate differences
    if result["foxpro"] and result["erpnext"]:
        fp = result["foxpro"]
        erp = result["erpnext"]
        
        if fp["customer"] and erp["customer"] and fp["customer"].lower() not in erp["customer"].lower():
            result["differences"].append({"field": "customer", "foxpro": fp["customer"], "erpnext": erp["customer"]})
        
        if fp["total"] and erp["total"]:
            diff_pct = abs(float(fp["total"]) - erp["total"]) / float(fp["total"]) * 100
            if diff_pct > 1:
                result["differences"].append({"field": "total", "foxpro": fp["total"], "erpnext": erp["total"], "diff_pct": round(diff_pct, 2)})
        
        if fp["lote_real"] and str(fp["lote_real"]) != str(erp["lote_real"] or ''):
            result["differences"].append({"field": "lote_real", "foxpro": fp["lote_real"], "erpnext": erp["lote_real"]})
        
        if fp["items_count"] != erp["items_count"]:
            result["differences"].append({"field": "items_count", "foxpro": fp["items_count"], "erpnext": erp["items_count"]})
    
    return result


# ==========================================
# Raven Chat Command Handlers
# ==========================================

def handle_migration_command(query: str) -> Optional[str]:
    """
    Handle migration-related chat commands
    
    Supported commands:
        - "scan migration 2024"
        - "scan migration from 00800 to 00850"
        - "fix folio 00752"
        - "fix folio 00752 confirm"
        - "compare folio 00752"
        - "migration report"
        - "migration report 2025"
    """
    query_lower = query.lower().strip()
    
    # Scan commands
    if "scan migration" in query_lower:
        parts = query_lower.split()
        
        # Check for year
        for p in parts:
            if p in ["2024", "2025"]:
                return scan_migration(year=int(p))
        
        # Check for range
        if "from" in query_lower and "to" in query_lower:
            try:
                from_idx = parts.index("from")
                to_idx = parts.index("to")
                start = parts[from_idx + 1]
                end = parts[to_idx + 1]
                return scan_migration(start=start, end=end)
            except:
                pass
        
        return "Usage: 'scan migration 2024' or 'scan migration from 00800 to 00850'"
    
    # Fix commands
    if "fix folio" in query_lower:
        parts = query_lower.split()
        try:
            folio_idx = parts.index("folio") + 1
            folio = parts[folio_idx]
            confirm = "confirm" in parts
            return fix_folio(folio, confirm=confirm)
        except:
            return "Usage: 'fix folio 00752' or 'fix folio 00752 confirm'"
    
    # Compare command
    if "compare folio" in query_lower:
        parts = query_lower.split()
        try:
            folio_idx = parts.index("folio") + 1
            folio = parts[folio_idx]
            result = compare_folio(folio)
            
            if result.get("error"):
                return f"❌ {result['error']}"
            
            output = f"📋 **Comparison for Folio {folio}**\n\n"
            
            if result["foxpro"]:
                fp = result["foxpro"]
                output += f"**FoxPro:**\n"
                output += f"- Customer: {fp['customer']}\n"
                output += f"- Date: {fp['date']}\n"
                output += f"- Total: ${fp['total']:,.2f}\n" if fp['total'] else ""
                output += f"- Lote Real: {fp['lote_real']}\n"
                output += f"- Items: {fp['items_count']}\n\n"
            else:
                output += "**FoxPro:** Not found\n\n"
            
            if result["erpnext"]:
                erp = result["erpnext"]
                output += f"**ERPNext ({erp['name']}):**\n"
                output += f"- Customer: {erp['customer']}\n"
                output += f"- Date: {erp['date']}\n"
                output += f"- Total: ${erp['total']:,.2f}\n"
                output += f"- Lote Real: {erp['lote_real']}\n"
                output += f"- Items: {erp['items_count']}\n\n"
            else:
                output += "**ERPNext:** Not found\n\n"
            
            if result["differences"]:
                output += "**⚠️ Differences:**\n"
                for d in result["differences"]:
                    output += f"- {d['field']}: FoxPro='{d['foxpro']}' vs ERPNext='{d['erpnext']}'\n"
            else:
                output += "✅ No differences found\n"
            
            return output
        except:
            return "Usage: 'compare folio 00752'"
    
    # Report command
    if "migration report" in query_lower:
        year = None
        if "2024" in query_lower:
            year = 2024
        elif "2025" in query_lower:
            year = 2025
        
        return get_migration_report(year=year)
    
    return None
