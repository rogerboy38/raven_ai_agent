"""
BOM Creator Validation Utilities
"""
import frappe
from typing import Dict, List, Tuple


def validate_item_exists(item_code: str) -> Tuple[bool, str]:
    """Check if item exists in Item master"""
    if frappe.db.exists("Item", item_code):
        return True, ""
    return False, f"Item '{item_code}' does not exist"


def validate_uom_exists(uom: str) -> Tuple[bool, str]:
    """Check if UOM exists"""
    if frappe.db.exists("UOM", uom):
        return True, ""
    return False, f"UOM '{uom}' does not exist"


def validate_bom_hierarchy(bom_creator_name: str) -> Dict:
    """Validate BOM Creator hierarchy structure"""
    bc = frappe.get_doc("BOM Creator", bom_creator_name)
    issues = []
    
    # Build index map
    idx_map = {str(item.idx): item for item in bc.items}
    
    for item in bc.items:
        # Check parent reference
        if item.parent_row_no and item.parent_row_no not in idx_map:
            issues.append({
                "item": item.item_code,
                "issue": f"References non-existent parent row {item.parent_row_no}"
            })
        
        # Check fg_reference_id
        if item.fg_reference_id:
            ref_exists = any(i.name == item.fg_reference_id for i in bc.items)
            if not ref_exists and item.fg_reference_id != bc.name:
                issues.append({
                    "item": item.item_code,
                    "issue": f"Invalid fg_reference_id '{item.fg_reference_id}'"
                })
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "total_items": len(bc.items)
    }


def get_bom_tree(bom_creator_name: str) -> Dict:
    """Get BOM Creator as a tree structure"""
    bc = frappe.get_doc("BOM Creator", bom_creator_name)
    
    # Build tree
    root = {
        "item_code": bc.item_code,
        "qty": bc.qty,
        "children": []
    }
    
    # Group items by parent
    items_by_parent = {}
    for item in bc.items:
        parent_key = item.fg_item or "root"
        if parent_key not in items_by_parent:
            items_by_parent[parent_key] = []
        items_by_parent[parent_key].append({
            "item_code": item.item_code,
            "qty": item.qty,
            "rate": item.rate,
            "uom": item.uom,
            "is_expandable": item.is_expandable
        })
    
    # Add first level children
    root["children"] = items_by_parent.get(bc.item_code, [])
    
    return root


def create_missing_items(bom_creator_name: str, item_group: str = "Products") -> Dict:
    """Auto-create missing items for BOM Creator"""
    bc = frappe.get_doc("BOM Creator", bom_creator_name)
    created = []
    
    # Check main item
    if not frappe.db.exists("Item", bc.item_code):
        item = frappe.get_doc({
            "doctype": "Item",
            "item_code": bc.item_code,
            "item_name": bc.item_name or bc.item_code,
            "item_group": item_group,
            "stock_uom": bc.uom or "Kg",
            "is_stock_item": 1
        })
        item.flags.ignore_permissions = True
        item.insert()
        created.append(bc.item_code)
    
    # Check child items
    for bom_item in bc.items:
        if not frappe.db.exists("Item", bom_item.item_code):
            item = frappe.get_doc({
                "doctype": "Item",
                "item_code": bom_item.item_code,
                "item_name": bom_item.item_name or bom_item.item_code,
                "item_group": bom_item.item_group or "Raw Materials",
                "stock_uom": bom_item.uom or "Kg",
                "is_stock_item": 1
            })
            item.flags.ignore_permissions = True
            item.insert()
            created.append(bom_item.item_code)
    
    if created:
        frappe.db.commit()
    
    return {
        "success": True,
        "created_count": len(created),
        "created_items": created[:10],  # Show first 10
        "message": f"Created {len(created)} missing items"
    }
