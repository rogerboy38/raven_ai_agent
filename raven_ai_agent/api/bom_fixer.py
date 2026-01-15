"""
BOM Label Fixer Module
Adds missing label items (LBLxxxx) to BOMs

Functions:
- check_and_fix_item(item_code, auto_fix=False) - Check/fix individual items
- fix_multiple_items(item_codes, auto_fix=False) - Bulk fix multiple items
- force_fix_submitted_bom(bom_name, label_code) - Direct SQL fix for stubborn BOMs
"""
import frappe
from frappe import _
from typing import List, Dict, Optional


def get_label_code(item_code: str) -> str:
    """Generate label item code from product item code"""
    # Strip any prefix and get base number
    base_code = item_code.replace("PROD-", "").replace("prod-", "").strip()
    return f"LBL{base_code}"


def check_item_label_exists(label_code: str) -> bool:
    """Check if label item exists in the system"""
    return frappe.db.exists("Item", label_code)


def check_bom_has_label(bom_name: str, label_code: str) -> bool:
    """Check if a BOM already has the label item"""
    return frappe.db.exists("BOM Item", {
        "parent": bom_name,
        "item_code": label_code
    })


def add_label_to_bom(bom_doc, label_code: str) -> bool:
    """Add label item to BOM items table"""
    # Check if label already exists
    for item in bom_doc.items:
        if item.item_code == label_code:
            return False  # Already exists
    
    # Get label item details
    label_item = frappe.get_doc("Item", label_code)
    
    # Add label as first item (or append)
    bom_doc.append("items", {
        "item_code": label_code,
        "item_name": label_item.item_name,
        "qty": 1,
        "rate": 0,
        "amount": 0,
        "stock_uom": label_item.stock_uom,
        "uom": label_item.stock_uom,
        "conversion_factor": 1,
        "source_warehouse": "",
        "description": label_item.description or f"Label for {bom_doc.item}"
    })
    
    return True


def check_and_fix_item(item_code: str, auto_fix: bool = False) -> Dict:
    """
    Check and optionally fix BOMs for an item by adding missing labels.
    
    Args:
        item_code: The product item code (e.g., "0302", "PROD-0302")
        auto_fix: If True, automatically fix issues. If False, just report.
    
    Returns:
        Dict with status, messages, and actions taken
    """
    result = {
        "item_code": item_code,
        "label_code": None,
        "label_exists": False,
        "boms_found": [],
        "boms_fixed": [],
        "boms_skipped": [],
        "errors": [],
        "success": True
    }
    
    try:
        # Generate label code
        label_code = get_label_code(item_code)
        result["label_code"] = label_code
        
        # Check if label item exists
        if not check_item_label_exists(label_code):
            result["label_exists"] = False
            result["errors"].append(f"Label item '{label_code}' does not exist in the system")
            result["success"] = False
            return result
        
        result["label_exists"] = True
        
        # Find all BOMs for this item
        boms = frappe.get_list("BOM", 
            filters={
                "item": ["like", f"%{item_code}%"]
            },
            fields=["name", "item", "docstatus", "is_active", "is_default"],
            order_by="creation desc"
        )
        
        if not boms:
            # Try exact match
            boms = frappe.get_list("BOM",
                filters={"item": item_code},
                fields=["name", "item", "docstatus", "is_active", "is_default"],
                order_by="creation desc"
            )
        
        result["boms_found"] = [b["name"] for b in boms]
        
        if not boms:
            result["errors"].append(f"No BOMs found for item '{item_code}'")
            return result
        
        for bom_info in boms:
            bom_name = bom_info["name"]
            docstatus = bom_info["docstatus"]
            
            # Check if label already present
            if check_bom_has_label(bom_name, label_code):
                result["boms_skipped"].append({
                    "bom": bom_name,
                    "reason": "Label already present",
                    "docstatus": docstatus
                })
                continue
            
            if not auto_fix:
                # Just report what needs fixing
                status_text = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(docstatus, "Unknown")
                result["boms_skipped"].append({
                    "bom": bom_name,
                    "reason": f"Needs label (Status: {status_text})",
                    "docstatus": docstatus,
                    "action_needed": True
                })
                continue
            
            # Auto-fix based on docstatus
            try:
                if docstatus == 0:
                    # Draft - add label directly
                    bom_doc = frappe.get_doc("BOM", bom_name)
                    if add_label_to_bom(bom_doc, label_code):
                        bom_doc.save(ignore_permissions=True)
                        result["boms_fixed"].append({
                            "bom": bom_name,
                            "action": "Added label to draft BOM"
                        })
                    
                elif docstatus == 1:
                    # Submitted - Cancel → Draft → Add → Re-submit
                    bom_doc = frappe.get_doc("BOM", bom_name)
                    
                    # Step 1: Cancel
                    bom_doc.cancel()
                    
                    # Step 2: Amend (create new version)
                    new_bom = frappe.copy_doc(bom_doc)
                    new_bom.docstatus = 0
                    new_bom.amended_from = bom_name
                    
                    # Step 3: Add label
                    add_label_to_bom(new_bom, label_code)
                    
                    # Step 4: Save and submit
                    new_bom.insert(ignore_permissions=True)
                    new_bom.submit()
                    
                    result["boms_fixed"].append({
                        "bom": bom_name,
                        "new_bom": new_bom.name,
                        "action": "Cancelled original, created amended version with label"
                    })
                    
                elif docstatus == 2:
                    # Cancelled - suggest creating new
                    result["boms_skipped"].append({
                        "bom": bom_name,
                        "reason": "BOM is cancelled. Create a new BOM version instead.",
                        "docstatus": docstatus
                    })
                    
            except Exception as e:
                result["errors"].append(f"Error fixing {bom_name}: {str(e)}")
                frappe.db.rollback()
        
        frappe.db.commit()
        
    except Exception as e:
        result["success"] = False
        result["errors"].append(str(e))
        frappe.db.rollback()
    
    return result


def fix_multiple_items(item_codes: List[str], auto_fix: bool = False) -> Dict:
    """
    Bulk fix multiple items' BOMs.
    
    Args:
        item_codes: List of item codes to fix
        auto_fix: If True, automatically fix. If False, just preview.
    
    Returns:
        Dict with summary and individual results
    """
    results = {
        "total_items": len(item_codes),
        "items_processed": 0,
        "boms_fixed": 0,
        "boms_skipped": 0,
        "errors": 0,
        "details": [],
        "mode": "AUTO-FIX" if auto_fix else "DRY-RUN (Preview)"
    }
    
    for item_code in item_codes:
        item_result = check_and_fix_item(item_code, auto_fix=auto_fix)
        results["details"].append(item_result)
        results["items_processed"] += 1
        results["boms_fixed"] += len(item_result.get("boms_fixed", []))
        results["boms_skipped"] += len(item_result.get("boms_skipped", []))
        if item_result.get("errors"):
            results["errors"] += len(item_result["errors"])
    
    return results


def force_fix_submitted_bom(bom_name: str, label_code: str) -> Dict:
    """
    ⚠️ NUCLEAR OPTION - Direct database insertion for stubborn BOMs.
    Uses SQL INSERT to bypass all validations.
    
    Args:
        bom_name: The BOM document name
        label_code: The label item code to add
    
    Returns:
        Dict with status and message
    """
    result = {
        "bom_name": bom_name,
        "label_code": label_code,
        "success": False,
        "message": ""
    }
    
    try:
        # Verify BOM exists
        if not frappe.db.exists("BOM", bom_name):
            result["message"] = f"BOM '{bom_name}' does not exist"
            return result
        
        # Verify label item exists
        if not frappe.db.exists("Item", label_code):
            result["message"] = f"Label item '{label_code}' does not exist"
            return result
        
        # Check if label already in BOM
        existing = frappe.db.sql("""
            SELECT name FROM `tabBOM Item`
            WHERE parent = %s AND item_code = %s
        """, (bom_name, label_code))
        
        if existing:
            result["success"] = True
            result["message"] = f"Label '{label_code}' already exists in BOM"
            return result
        
        # Get label item details
        label_item = frappe.get_doc("Item", label_code)
        
        # Get max idx for ordering
        max_idx = frappe.db.sql("""
            SELECT MAX(idx) FROM `tabBOM Item` WHERE parent = %s
        """, (bom_name,))[0][0] or 0
        
        # Generate unique name for BOM Item
        import time
        item_name = f"{bom_name}-label-{int(time.time())}"
        
        # Direct SQL INSERT
        frappe.db.sql("""
            INSERT INTO `tabBOM Item` (
                name, parent, parenttype, parentfield, idx,
                item_code, item_name, qty, rate, amount,
                stock_uom, uom, conversion_factor,
                description, docstatus, creation, modified, owner, modified_by
            ) VALUES (
                %s, %s, 'BOM', 'items', %s,
                %s, %s, 1, 0, 0,
                %s, %s, 1,
                %s, 1, NOW(), NOW(), 'Administrator', 'Administrator'
            )
        """, (
            item_name, bom_name, max_idx + 1,
            label_code, label_item.item_name,
            label_item.stock_uom, label_item.stock_uom,
            label_item.description or f"Label for {bom_name}"
        ))
        
        frappe.db.commit()
        
        result["success"] = True
        result["message"] = f"✅ Force-added label '{label_code}' to BOM '{bom_name}' via SQL"
        
    except Exception as e:
        result["message"] = f"Error: {str(e)}"
        frappe.db.rollback()
    
    return result


def get_items_missing_labels(item_codes: List[str] = None) -> List[Dict]:
    """
    Get a list of items that are missing labels in their BOMs.
    
    Args:
        item_codes: Optional list to check. If None, checks all active BOMs.
    
    Returns:
        List of items missing labels
    """
    missing = []
    
    if item_codes:
        for item_code in item_codes:
            label_code = get_label_code(item_code)
            if not check_item_label_exists(label_code):
                missing.append({
                    "item_code": item_code,
                    "label_code": label_code,
                    "issue": "Label item does not exist"
                })
                continue
            
            # Check BOMs
            boms = frappe.get_list("BOM",
                filters={"item": ["like", f"%{item_code}%"], "docstatus": ["!=", 2]},
                fields=["name", "item", "docstatus"]
            )
            
            for bom in boms:
                if not check_bom_has_label(bom["name"], label_code):
                    missing.append({
                        "item_code": item_code,
                        "label_code": label_code,
                        "bom": bom["name"],
                        "docstatus": bom["docstatus"],
                        "issue": "BOM missing label"
                    })
    
    return missing


def get_bom_details(bom_name: str) -> Dict:
    """
    Get complete BOM details including all items.
    
    Args:
        bom_name: The BOM document name
    
    Returns:
        Dict with BOM info and all items
    """
    result = {
        "success": False,
        "bom_name": bom_name,
        "item": None,
        "docstatus": None,
        "status_text": None,
        "is_active": False,
        "is_default": False,
        "total_cost": 0,
        "items": [],
        "operations": [],
        "message": ""
    }
    
    try:
        if not frappe.db.exists("BOM", bom_name):
            result["message"] = f"BOM '{bom_name}' not found"
            return result
        
        bom = frappe.get_doc("BOM", bom_name)
        
        status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
        
        result["success"] = True
        result["item"] = bom.item
        result["item_name"] = bom.item_name if hasattr(bom, 'item_name') else bom.item
        result["docstatus"] = bom.docstatus
        result["status_text"] = status_map.get(bom.docstatus, "Unknown")
        result["is_active"] = bom.is_active
        result["is_default"] = bom.is_default
        result["total_cost"] = bom.total_cost if hasattr(bom, 'total_cost') else 0
        result["quantity"] = bom.quantity if hasattr(bom, 'quantity') else 1
        
        # Get all items
        for item in bom.items:
            result["items"].append({
                "idx": item.idx,
                "item_code": item.item_code,
                "item_name": item.item_name,
                "qty": item.qty,
                "rate": item.rate or 0,
                "amount": item.amount or 0,
                "uom": item.uom,
                "source_warehouse": item.source_warehouse or ""
            })
        
        # Get operations if any
        if hasattr(bom, 'operations') and bom.operations:
            for op in bom.operations:
                result["operations"].append({
                    "idx": op.idx,
                    "operation": op.operation,
                    "workstation": op.workstation,
                    "time_in_mins": op.time_in_mins
                })
        
    except Exception as e:
        result["message"] = str(e)
    
    return result


# Whitelist for Frappe API access
@frappe.whitelist()
def api_check_and_fix_item(item_code: str, auto_fix: bool = False) -> Dict:
    """API wrapper for check_and_fix_item"""
    return check_and_fix_item(item_code, auto_fix=auto_fix)


@frappe.whitelist()
def api_fix_multiple_items(item_codes: str, auto_fix: bool = False) -> Dict:
    """API wrapper for fix_multiple_items"""
    import json
    codes = json.loads(item_codes) if isinstance(item_codes, str) else item_codes
    return fix_multiple_items(codes, auto_fix=auto_fix)


@frappe.whitelist()
def api_force_fix_bom(bom_name: str, label_code: str) -> Dict:
    """API wrapper for force_fix_submitted_bom"""
    return force_fix_submitted_bom(bom_name, label_code)
