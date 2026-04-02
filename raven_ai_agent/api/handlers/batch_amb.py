"""
Batch AMB Command Handler for Raven AI Agent
Implements 10 batch management commands following the existing handler pattern.
"""
import frappe
import re
from typing import Optional, Dict, List


class BatchAMBMixin:
    """Mixin for _handle_batch_commands"""

    def _handle_batch_commands(self, query: str, query_lower: str, is_confirm: bool = False) -> Optional[Dict]:
        """Dispatched from execute_workflow_command for batch-related queries"""
        
        # ==================== HELP COMMAND ====================
        if "help" in query_lower and "batch" in query_lower:
            return self._handle_batch_help()
        
        # ==================== BATCH CREATE ====================
        # @ai batch create <item_code> <work_order>
        if query_lower.startswith("batch create"):
            match = re.search(r'batch create\s+(\S+)\s+(\S+)', query, re.IGNORECASE)
            if match:
                item_code = match.group(1)
                work_order = match.group(2)
                return self._handle_batch_create(item_code, work_order)
            return {"success": False, "error": "Usage: @ai batch create <item_code> <work_order>"}
        
        # ==================== BATCH SUBLOT ====================
        # @ai batch sublot <parent_batch>
        if query_lower.startswith("batch sublot"):
            match = re.search(r'batch sublot\s+(\S+)', query, re.IGNORECASE)
            if match:
                parent_batch = match.group(1)
                return self._handle_batch_sublot(parent_batch)
            return {"success": False, "error": "Usage: @ai batch sublot <parent_batch>"}
        
        # ==================== BATCH CONTAINER ====================
        # @ai batch container <parent_sublot>
        if query_lower.startswith("batch container"):
            match = re.search(r'batch container\s+(\S+)', query, re.IGNORECASE)
            if match:
                parent_sublot = match.group(1)
                return self._handle_batch_container(parent_sublot)
            return {"success": False, "error": "Usage: @ai batch container <parent_sublot>"}
        
        # ==================== BATCH SERIAL ====================
        # @ai batch serial <batch_name> [quantity] [prefix]
        if query_lower.startswith("batch serial"):
            match = re.search(r'batch serial\s+(\S+)(?:\s+(\d+))?(?:\s+(\S+))?', query, re.IGNORECASE)
            if match:
                batch_name = match.group(1)
                quantity = int(match.group(2)) if match.group(2) else 5
                prefix = match.group(3)
                return self._handle_batch_serial(batch_name, quantity, prefix)
            return {"success": False, "error": "Usage: @ai batch serial <batch_name> [quantity] [prefix]"}
        
        # ==================== BATCH WEIGH ====================
        # @ai batch weigh <batch_name> <barrel_serial> <gross_weight>
        if query_lower.startswith("batch weigh"):
            match = re.search(r'batch weigh\s+(\S+)\s+(\S+)\s+([\d.]+)', query, re.IGNORECASE)
            if match:
                batch_name = match.group(1)
                barrel_serial = match.group(2)
                gross_weight = float(match.group(3))
                return self._handle_batch_weigh(batch_name, barrel_serial, gross_weight)
            return {"success": False, "error": "Usage: @ai batch weigh <batch_name> <barrel_serial> <gross_weight>"}
        
        # ==================== BATCH STATUS ====================
        # @ai batch status <batch_name>
        if query_lower.startswith("batch status"):
            match = re.search(r'batch status\s+(\S+)', query, re.IGNORECASE)
            if match:
                batch_name = match.group(1)
                return self._handle_batch_status(batch_name)
            return {"success": False, "error": "Usage: @ai batch status <batch_name>"}
        
        # ==================== BATCH LIST ====================
        # @ai batch list [level] [status]
        if query_lower.startswith("batch list"):
            match = re.search(r'batch list(?:\s+(\d))?(?:\s+(\S+))?', query, re.IGNORECASE)
            level = match.group(1) if match.group(1) else None
            status = match.group(2) if match.group(2) else None
            return self._handle_batch_list(level, status)
        
        # ==================== BATCH TREE ====================
        # @ai batch tree <batch_name>
        if query_lower.startswith("batch tree"):
            match = re.search(r'batch tree\s+(\S+)', query, re.IGNORECASE)
            if match:
                batch_name = match.group(1)
                return self._handle_batch_tree(batch_name)
            return {"success": False, "error": "Usage: @ai batch tree <batch_name>"}
        
        # ==================== BATCH PIPELINE ====================
        # @ai batch pipeline <batch_name> <new_status>
        if query_lower.startswith("batch pipeline"):
            match = re.search(r'batch pipeline\s+(\S+)\s+(\S+)', query, re.IGNORECASE)
            if match:
                batch_name = match.group(1)
                new_status = match.group(2)
                return self._handle_batch_pipeline(batch_name, new_status)
            return {"success": False, "error": "Usage: @ai batch pipeline <batch_name> <new_status>"}
        
        return None

    def _handle_batch_help(self) -> Dict:
        """Return help message with all available batch commands"""
        help_text = """
📦 **Batch AMB Commands**

| Command | Description |
|---------|-------------|
| `@ai batch create <item> <wo>` | Create Level 1 batch |
| `@ai batch sublot <parent>` | Create Level 2 sublot |
| `@ai batch container <parent>` | Create Level 3 container |
| `@ai batch serial <batch> [qty] [prefix]` | Generate serials for L3 |
| `@ai batch weigh <batch> <serial> <weight>` | Update barrel weight |
| `@ai batch status <batch>` | Show batch info |
| `@ai batch list [level] [status]` | List recent batches |
| `@ai batch tree <batch>` | Show hierarchy tree |
| `@ai batch pipeline <batch> <status>` | Update pipeline status |
| `@ai batch help` | Show this help |

**Pipeline Statuses:** Draft, WO Linked, In Production, Weighing, QI Pending, QI Passed, COA Ready, Ready for Delivery, Delivered, Closed
"""
        return {"success": True, "message": help_text}

    def _handle_batch_create(self, item_code: str, work_order: str) -> Dict:
        """Create a new Level 1 Batch AMB"""
        try:
            # Validate work order exists
            wo = frappe.get_doc("Work Order", work_order)
            
            # Create new batch
            batch = frappe.new_doc("Batch AMB")
            batch.naming_series = "LOTE-.#####"
            batch.work_order_ref = work_order
            batch.item_to_manufacture = wo.production_item
            batch.company = wo.company
            
            # Set default pipeline status
            if batch.meta.get_field("pipeline_status"):
                batch.pipeline_status = "Draft"
            
            batch.insert(ignore_permissions=True)
            frappe.db.commit()
            
            site_name = frappe.local.site
            batch_link = f"https://{site_name}/app/batch-amb/{batch.name}"
            
            return {
                "success": True,
                "message": f"✅ **Batch Created**\n\n"
                           f"**Name:** [{batch.name}]({batch_link})\n"
                           f"**Title:** {batch.title}\n"
                           f"**Golden Number:** {batch.custom_golden_number}\n"
                           f"**Level:** {batch.custom_batch_level}\n"
                           f"**Item:** {batch.item_to_manufacture}\n"
                           f"**Work Order:** {work_order}"
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Work Order '{work_order}' not found"}
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "error": f"Error creating batch: {str(e)}"}

    def _handle_batch_sublot(self, parent_batch: str) -> Dict:
        """Create a Level 2 sublot under a Level 1 batch"""
        try:
            parent = frappe.get_doc("Batch AMB", parent_batch)
            
            # Validate parent is Level 1
            if parent.custom_batch_level != '1':
                return {"success": False, "error": f"Parent batch must be Level 1, got Level {parent.custom_batch_level}"}
            
            # Create sublot
            batch = frappe.new_doc("Batch AMB")
            batch.naming_series = "LOTE-.#####"
            batch.work_order_ref = parent.work_order_ref
            batch.item_to_manufacture = parent.item_to_manufacture
            batch.company = parent.company
            batch.custom_batch_level = '2'
            batch.parent_batch_amb = parent_batch
            batch.is_group = 0
            
            if batch.meta.get_field("pipeline_status"):
                batch.pipeline_status = "Draft"
            
            batch.insert(ignore_permissions=True)
            frappe.db.commit()
            
            site_name = frappe.local.site
            batch_link = f"https://{site_name}/app/batch-amb/{batch.name}"
            
            return {
                "success": True,
                "message": f"✅ **Sublot Created**\n\n"
                           f"**Name:** [{batch.name}]({batch_link})\n"
                           f"**Title:** {batch.title}\n"
                           f"**Parent:** {parent_batch}\n"
                           f"**Level:** 2"
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Parent batch '{parent_batch}' not found"}
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "error": f"Error creating sublot: {str(e)}"}

    def _handle_batch_container(self, parent_sublot: str) -> Dict:
        """Create a Level 3 container under a Level 2 sublot"""
        try:
            parent = frappe.get_doc("Batch AMB", parent_sublot)
            
            # Validate parent is Level 2
            if parent.custom_batch_level != '2':
                return {"success": False, "error": f"Parent must be Level 2, got Level {parent.custom_batch_level}"}
            
            # Create container
            batch = frappe.new_doc("Batch AMB")
            batch.naming_series = "LOTE-.#####"
            batch.work_order_ref = parent.work_order_ref
            batch.item_to_manufacture = parent.item_to_manufacture
            batch.company = parent.company
            batch.custom_batch_level = '3'
            batch.parent_batch_amb = parent_sublot
            batch.is_group = 0
            
            if batch.meta.get_field("pipeline_status"):
                batch.pipeline_status = "Draft"
            
            batch.insert(ignore_permissions=True)
            frappe.db.commit()
            
            site_name = frappe.local.site
            batch_link = f"https://{site_name}/app/batch-amb/{batch.name}"
            
            return {
                "success": True,
                "message": f"✅ **Container Created**\n\n"
                           f"**Name:** [{batch.name}]({batch_link})\n"
                           f"**Title:** {batch.title}\n"
                           f"**Parent:** {parent_sublot}\n"
                           f"**Level:** 3"
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Parent sublot '{parent_sublot}' not found"}
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "error": f"Error creating container: {str(e)}"}

    def _handle_batch_serial(self, batch_name: str, quantity: int = 5, prefix: str = None) -> Dict:
        """Generate serial numbers for a Level 3 batch"""
        try:
            batch = frappe.get_doc("Batch AMB", batch_name)
            
            # Validate level 3
            if batch.custom_batch_level != '3':
                return {"success": False, "error": f"Batch must be Level 3, got Level {batch.custom_batch_level}"}
            
            # Import and call the generator
            from amb_w_tds.amb_w_tds.doctype.batch_amb.batch_amb import BatchAMB
            generator = BatchAMB(batch)
            result = generator.generate_serial_numbers(quantity, prefix)
            
            if result.get("status") == "success":
                serials = result.get("serials", [])
                serial_list = "\n".join([f"  • {s}" for s in serials[:10]])
                if len(serials) > 10:
                    serial_list += f"\n  ... and {len(serials) - 10} more"
                
                return {
                    "success": True,
                    "message": f"✅ **Serials Generated**\n\n"
                               f"**Batch:** {batch_name}\n"
                               f"**Count:** {len(serials)}\n"
                               f"**Serials:**\n{serial_list}"
                }
            else:
                return {"success": False, "error": result.get("message", "Failed to generate serials")}
        except ImportError:
            return {"success": False, "error": "amb_w_tds app not installed"}
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Batch '{batch_name}' not found"}
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "error": f"Error generating serials: {str(e)}"}

    def _handle_batch_weigh(self, batch_name: str, barrel_serial: str, gross_weight: float) -> Dict:
        """Update barrel weight and calculate net weight"""
        try:
            batch = frappe.get_doc("Batch AMB", batch_name)
            
            # Find the barrel
            barrel = None
            for row in batch.container_barrels:
                if row.serial_number == barrel_serial:
                    barrel = row
                    break
            
            if not barrel:
                return {"success": False, "error": f"Barrel '{barrel_serial}' not found in batch"}
            
            # Update weights
            barrel.gross_weight = gross_weight
            if barrel.tara_weight:
                barrel.net_weight = gross_weight - barrel.tara_weight
            
            batch.save(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                "success": True,
                "message": f"✅ **Weight Updated**\n\n"
                           f"**Barrel:** {barrel_serial}\n"
                           f"**Gross Weight:** {barrel.gross_weight}\n"
                           f"**Tara Weight:** {barrel.tara_weight or 0}\n"
                           f"**Net Weight:** {barrel.net_weight}"
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Batch '{batch_name}' not found"}
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "error": f"Error updating weight: {str(e)}"}

    def _handle_batch_status(self, batch_name: str) -> Dict:
        """Return full batch info"""
        try:
            batch = frappe.get_doc("Batch AMB", batch_name)
            
            site_name = frappe.local.site
            batch_link = f"https://{site_name}/app/batch-amb/{batch_name}"
            
            # Base info
            info = f"📦 **Batch Status**\n\n"
            info += f"**Name:** [{batch_name}]({batch_link})\n"
            info += f"**Title:** {batch.title}\n"
            info += f"**Level:** {batch.custom_batch_level}\n"
            info += f"**Pipeline:** {batch.pipeline_status or 'Not set'}\n"
            info += f"**Golden Number:** {batch.custom_golden_number or 'N/A'}\n"
            
            if batch.parent_batch_amb:
                info += f"**Parent:** {batch.parent_batch_amb}\n"
            
            # Level 3 specific info
            if batch.custom_batch_level == '3':
                barrels = batch.container_barrels
                info += f"\n**Container Barrels:** {len(barrels)}\n"
                
                total_gross = sum((b.gross_weight or 0) for b in barrels)
                total_tara = sum((b.tara_weight or 0) for b in barrels)
                total_net = sum((b.net_weight or 0) for b in barrels)
                
                info += f"**Total Gross:** {total_gross}\n"
                info += f"**Total Tara:** {total_tara}\n"
                info += f"**Total Net:** {total_net}\n"
            
            return {"success": True, "message": info}
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Batch '{batch_name}' not found"}
        except Exception as e:
            return {"success": False, "error": f"Error: {str(e)}"}

    def _handle_batch_list(self, level: str = None, status: str = None) -> Dict:
        """List recent batches with optional filters"""
        try:
            filters = {}
            if level:
                filters["custom_batch_level"] = level
            if status:
                filters["pipeline_status"] = status
            
            batches = frappe.get_all(
                "Batch AMB",
                filters=filters,
                fields=["name", "title", "custom_batch_level", "pipeline_status", "modified"],
                order_by="modified desc",
                limit=10
            )
            
            if not batches:
                return {"success": True, "message": "No batches found"}
            
            site_name = frappe.local.site
            rows = []
            for b in batches:
                link = f"[{b.name}](https://{site_name}/app/batch-amb/{b.name})"
                rows.append(f"| {link} | {b.title} | L{b.custom_batch_level} | {b.pipeline_status or '-'} |")
            
            header = "| Name | Title | Level | Pipeline |\n"
            header += "|------|-------|-------|----------|\n"
            
            return {
                "success": True,
                "message": f"📋 **Recent Batches**\n\n{header}" + "\n".join(rows)
            }
        except Exception as e:
            return {"success": False, "error": f"Error listing batches: {str(e)}"}

    def _handle_batch_tree(self, batch_name: str) -> Dict:
        """Show hierarchy tree for a batch"""
        try:
            batch = frappe.get_doc("Batch AMB", batch_name)
            
            site_name = frappe.local.site
            
            # Build tree recursively
            def build_tree(name: str, indent: int = 0) -> List[tuple]:
                result = []
                prefix = "  " * indent
                
                batch_doc = frappe.get_doc("Batch AMB", name)
                link = f"[{name}](https://{site_name}/app/batch-amb/{name})"
                result.append((indent, f"{prefix}└─ {link} ({batch_doc.title})"))
                
                # Get child batches
                children = frappe.get_all(
                    "Batch AMB",
                    filters={"parent_batch_amb": name},
                    fields=["name"],
                    order_by="custom_consecutive_number"
                )
                
                for child in children:
                    result.extend(build_tree(child.name, indent + 1))
                
                return result
            
            tree_lines = [f"🌳 **Hierarchy Tree: {batch_name}**\n"]
            tree_lines.append(f"**Root:** [{batch_name}](https://{site_name}/app/batch-amb/{batch_name}) ({batch.title})")
            tree_lines.append("")
            
            # Get direct children
            children = frappe.get_all(
                "Batch AMB",
                filters={"parent_batch_amb": batch_name},
                fields=["name", "title", "custom_batch_level"],
                order_by="custom_batch_level, custom_consecutive_number"
            )
            
            if not children:
                tree_lines.append("_No child batches_")
            else:
                for child in children:
                    child_link = f"[{child.name}](https://{site_name}/app/batch-amb/{child.name})"
                    tree_lines.append(f"  └─ {child_link} ({child.title}) - Level {child.custom_batch_level}")
            
            return {"success": True, "message": "\n".join(tree_lines)}
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Batch '{batch_name}' not found"}
        except Exception as e:
            return {"success": False, "error": f"Error: {str(e)}"}

    def _handle_batch_pipeline(self, batch_name: str, new_status: str) -> Dict:
        """Update pipeline status"""
        valid_statuses = [
            "Draft", "WO Linked", "In Production", "Weighing",
            "QI Pending", "QI Passed", "COA Ready", "Ready for Delivery",
            "Delivered", "Closed"
        ]
        
        # Normalize status
        new_status_normalized = new_status.strip()
        
        # Find matching status
        matched_status = None
        for vs in valid_statuses:
            if vs.lower() == new_status_normalized.lower():
                matched_status = vs
                break
        
        if not matched_status:
            return {
                "success": False,
                "error": f"Invalid status. Valid: {', '.join(valid_statuses)}"
            }
        
        try:
            batch = frappe.get_doc("Batch AMB", batch_name)
            old_status = batch.pipeline_status or "Not set"
            
            batch.pipeline_status = matched_status
            batch.save(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                "success": True,
                "message": f"✅ **Pipeline Updated**\n\n"
                           f"**Batch:** {batch_name}\n"
                           f"**Old Status:** {old_status}\n"
                           f"**New Status:** {matched_status}"
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Batch '{batch_name}' not found"}
        except Exception as e:
            frappe.db.rollback()
            return {"success": False, "error": f"Error updating status: {str(e)}"}
