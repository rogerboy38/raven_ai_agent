"""
BOM Creator Migration Scripts
Export/Import BOM Creator with all Items between environments
"""
import frappe
import json
from datetime import datetime
from typing import Dict, List


def export_bom_creator(bom_name: str, output_path: str = None) -> Dict:
    """
    Export BOM Creator with all associated Items
    
    Args:
        bom_name: Name of BOM Creator to export
        output_path: Optional output file path (default: /tmp/bom_export_TIMESTAMP.json)
    
    Returns:
        Dict with export status and file path
    """
    print("=" * 80)
    print("BOM EXPORT SCRIPT - SANDBOX TO TEST/PROD")
    print("=" * 80)
    
    try:
        # Phase 1: Get BOM Creator
        print("\nPhase 1: Exporting BOM Creator document...")
        bom = frappe.get_doc("BOM Creator", bom_name)
        print(f"✅ Found BOM: {bom.name}")
        print(f"   - Item Code: {bom.item_code}")
        print(f"   - Items count: {len(bom.items)}")
        
        # Phase 2: Collect all item codes
        print("\nPhase 2: Collecting all item codes...")
        item_codes = set()
        item_codes.add(bom.item_code)
        for row in bom.items:
            item_codes.add(row.item_code)
            if row.fg_item:
                item_codes.add(row.fg_item)
        print(f"✅ Found {len(item_codes)} unique items")
        
        # Phase 3: Export Item master data
        print("\nPhase 3: Exporting Item master data...")
        items_data = []
        for item_code in item_codes:
            if frappe.db.exists("Item", item_code):
                item = frappe.get_doc("Item", item_code)
                item_dict = item.as_dict()
                # Clean up non-essential fields
                for key in ['modified', 'modified_by', 'creation', 'owner', 'docstatus', 'idx']:
                    item_dict.pop(key, None)
                # Ensure product_key exists
                if not item_dict.get('product_key'):
                    item_dict['product_key'] = item_code.split('-')[0] if '-' in item_code else item_code
                items_data.append(item_dict)
                print(f"   ✅ Exported: {item_code}")
            else:
                print(f"   ⚠️ Item not found: {item_code}")
        
        # Phase 4: Prepare BOM data
        print("\nPhase 4: Preparing BOM Creator data...")
        bom_dict = bom.as_dict()
        # Clean up
        for key in ['modified', 'modified_by', 'creation', 'owner', 'docstatus']:
            bom_dict.pop(key, None)
        
        # Phase 5: Create export package
        print("\nPhase 5: Creating export package...")
        export_data = {
            "metadata": {
                "export_date": datetime.now().isoformat(),
                "source_site": frappe.local.site,
                "bom_name": bom_name,
                "total_items": len(items_data),
                "total_bom_rows": len(bom.items)
            },
            "items": items_data,
            "bom_creator": bom_dict
        }
        
        # Write to file
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"/tmp/bom_export_{timestamp}.json"
        
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        print("\n" + "=" * 80)
        print("✅ EXPORT COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        print(f"Export file: {output_path}")
        print(f"Total Items: {len(items_data)}")
        print(f"Total BOM Rows: {len(bom.items)}")
        
        return {
            "success": True,
            "file_path": output_path,
            "items_count": len(items_data),
            "bom_rows": len(bom.items)
        }
        
    except Exception as e:
        print(f"\n❌ Export failed: {str(e)}")
        return {"success": False, "error": str(e)}


def import_bom_creator(json_file: str, recreate_if_exists: bool = False) -> Dict:
    """
    Import BOM Creator with all associated Items
    
    Args:
        json_file: Path to export JSON file
        recreate_if_exists: If True, delete and recreate existing BOM
    
    Returns:
        Dict with import status
    """
    print("=" * 80)
    print("BOM IMPORT SCRIPT - TEST/PROD ENVIRONMENT")
    print("=" * 80)
    
    try:
        # Phase 1: Load export file
        print("\nPhase 1: Loading export file...")
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        metadata = data.get("metadata", {})
        print(f"✅ Loaded: {json_file}")
        print(f"   Export Date: {metadata.get('export_date')}")
        print(f"   Source: {metadata.get('source_site')}")
        print(f"   Total Items: {metadata.get('total_items')}")
        print(f"   Total BOM Rows: {metadata.get('total_bom_rows')}")
        
        # Phase 2: Import Items
        print("\nPhase 2: Importing Item master data...")
        items_created = 0
        items_skipped = 0
        
        for item_data in data.get("items", []):
            item_code = item_data.get("item_code") or item_data.get("name")
            
            if frappe.db.exists("Item", item_code):
                print(f"   ⏭️ Skipped (exists): {item_code}")
                items_skipped += 1
                continue
            
            # Create item
            item_data["doctype"] = "Item"
            item_data.pop("name", None)
            
            try:
                item = frappe.get_doc(item_data)
                item.flags.ignore_permissions = True
                item.flags.ignore_mandatory = True
                item.insert()
                print(f"   ✅ Created: {item_code}")
                items_created += 1
            except Exception as e:
                print(f"   ❌ Failed: {item_code} - {str(e)}")
        
        frappe.db.commit()
        print(f"\n   Summary: {items_created} created, {items_skipped} skipped")
        
        # Phase 3: Create BOM Creator
        print("\nPhase 3: Creating BOM Creator document...")
        bom_data = data.get("bom_creator", {})
        bom_name = bom_data.get("name")
        
        if frappe.db.exists("BOM Creator", bom_name):
            if recreate_if_exists:
                print(f"   ⚠️ Deleting existing BOM: {bom_name}")
                frappe.delete_doc("BOM Creator", bom_name, force=True)
                frappe.db.commit()
            else:
                print(f"   ⚠️ BOM Creator '{bom_name}' already exists!")
                return {
                    "success": False,
                    "error": f"BOM Creator '{bom_name}' already exists. Set recreate_if_exists=True to overwrite."
                }
        
        # Create BOM Creator (without items first)
        bom_items = bom_data.pop("items", [])
        bom_data["doctype"] = "BOM Creator"
        bom_data["items"] = []
        
        bom = frappe.get_doc(bom_data)
        bom.flags.ignore_permissions = True
        bom.flags.ignore_mandatory = True
        bom.insert()
        print(f"✅ Created BOM: {bom.name}")
        
        # Phase 4: Add BOM items
        print("\nPhase 4: Adding BOM items...")
        for i, item_row in enumerate(bom_items):
            item_row.pop("name", None)
            item_row.pop("parent", None)
            item_row.pop("parentfield", None)
            item_row.pop("parenttype", None)
            item_row["doctype"] = "BOM Creator Item"
            bom.append("items", item_row)
            
            if (i + 1) % 10 == 0:
                print(f"   ... {i + 1} items added")
        
        bom.flags.ignore_permissions = True
        bom.save()
        frappe.db.commit()
        print(f"✅ BOM saved with {len(bom.items)} items")
        
        # Phase 5: Verify
        print("\nPhase 5: Verifying import...")
        expected = metadata.get("total_bom_rows", 0)
        actual = len(bom.items)
        print(f"   Expected items: {expected}")
        print(f"   Actual items: {actual}")
        
        if expected == actual:
            print("   ✅ Item count matches!")
        else:
            print(f"   ⚠️ Count mismatch: expected {expected}, got {actual}")
        
        print("\n" + "=" * 80)
        print("✅ IMPORT COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        print(f"BOM Name: {bom.name}")
        print(f"Items Created: {items_created}")
        print(f"Items Skipped: {items_skipped}")
        print(f"BOM Rows Added: {len(bom.items)}")
        print(f"\nView at: /app/bom-creator/{bom.name}")
        
        return {
            "success": True,
            "bom_name": bom.name,
            "items_created": items_created,
            "items_skipped": items_skipped,
            "bom_rows": len(bom.items)
        }
        
    except Exception as e:
        frappe.db.rollback()
        print(f"\n❌ Import failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


# API Endpoints
@frappe.whitelist()
def export_bom(bom_name: str) -> Dict:
    """API: Export BOM Creator"""
    return export_bom_creator(bom_name)


@frappe.whitelist()
def import_bom(json_file: str, recreate: bool = False) -> Dict:
    """API: Import BOM Creator"""
    return import_bom_creator(json_file, recreate)
