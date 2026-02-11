"""
Sales Order Follow-up AI Agent
Tracks and advances Sales Orders through the complete fulfillment cycle
Based on SOP: Ciclo de Venta a Compra en ERPNext
"""
import frappe
from typing import Dict, List, Optional
from frappe.utils import nowdate, getdate


class SalesOrderFollowupAgent:
    """AI Agent for Sales Order follow-up and fulfillment tracking"""
    
    # Status workflow mapping
    STATUS_NEXT_ACTIONS = {
        "Draft": "Submit the Sales Order",
        "To Deliver and Bill": "Check inventory → Create Delivery Note or Material Request",
        "To Deliver": "Create Delivery Note",
        "To Bill": "Create Sales Invoice",
        "Completed": "Order fully fulfilled",
        "Cancelled": "Order was cancelled - no action needed"
    }
    
    def __init__(self, user: str = None):
        self.user = user or frappe.session.user
        self.site_name = frappe.local.site
    
    def make_link(self, doctype: str, name: str) -> str:
        """Generate clickable markdown link"""
        slug = doctype.lower().replace(" ", "-")
        return f"[{name}](https://{self.site_name}/app/{slug}/{name})"
    
    # ========== STATUS & TRACKING ==========
    
    def get_so_status(self, so_name: str) -> Dict:
        """Get detailed status of a specific Sales Order"""
        try:
            so = frappe.get_doc("Sales Order", so_name)
            
            # Get linked documents
            delivery_notes = frappe.get_all("Delivery Note Item", 
                filters={"against_sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["parent"], distinct=True)
            
            sales_invoices = frappe.get_all("Sales Invoice Item",
                filters={"sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["parent"], distinct=True)
            
            material_requests = frappe.get_all("Material Request Item",
                filters={"sales_order": so_name, "docstatus": ["!=", 2]},
                fields=["parent"], distinct=True)
            
            # Check inventory for each item
            inventory_status = []
            for item in so.items:
                available = frappe.db.get_value("Bin", 
                    {"item_code": item.item_code, "warehouse": item.warehouse},
                    "actual_qty") or 0
                inventory_status.append({
                    "item_code": item.item_code,
                    "ordered_qty": item.qty,
                    "available_qty": available,
                    "sufficient": available >= item.qty
                })
            
            all_sufficient = all(i["sufficient"] for i in inventory_status)
            
            return {
                "success": True,
                "so_name": so.name,
                "link": self.make_link("Sales Order", so.name),
                "customer": so.customer,
                "status": so.status,
                "delivery_status": so.delivery_status,
                "billing_status": so.billing_status,
                "grand_total": so.grand_total,
                "delivery_date": str(so.delivery_date) if so.delivery_date else None,
                "next_action": self.STATUS_NEXT_ACTIONS.get(so.status, "Review order status"),
                "inventory_sufficient": all_sufficient,
                "inventory_details": inventory_status,
                "linked_documents": {
                    "delivery_notes": [d.parent for d in delivery_notes],
                    "sales_invoices": [i.parent for i in sales_invoices],
                    "material_requests": [m.parent for m in material_requests]
                }
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_pending_orders(self, limit: int = 20) -> Dict:
        """List all Sales Orders pending delivery or billing"""
        try:
            orders = frappe.get_all("Sales Order",
                filters={
                    "docstatus": 1,
                    "status": ["in", ["To Deliver and Bill", "To Deliver", "To Bill"]]
                },
                fields=["name", "customer", "status", "grand_total", "delivery_date", "transaction_date"],
                order_by="delivery_date asc",
                limit=limit)
            
            result = []
            for so in orders:
                result.append({
                    "name": so.name,
                    "link": self.make_link("Sales Order", so.name),
                    "customer": so.customer,
                    "status": so.status,
                    "grand_total": so.grand_total,
                    "delivery_date": str(so.delivery_date) if so.delivery_date else "Not set",
                    "next_action": self.STATUS_NEXT_ACTIONS.get(so.status, "Review")
                })
            
            return {
                "success": True,
                "count": len(result),
                "orders": result
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def check_inventory(self, so_name: str) -> Dict:
        """Check item availability for a Sales Order"""
        try:
            so = frappe.get_doc("Sales Order", so_name)
            
            items = []
            all_available = True
            
            for item in so.items:
                available = frappe.db.get_value("Bin",
                    {"item_code": item.item_code, "warehouse": item.warehouse},
                    "actual_qty") or 0
                
                shortage = max(0, item.qty - available)
                sufficient = available >= item.qty
                
                if not sufficient:
                    all_available = False
                
                items.append({
                    "item_code": item.item_code,
                    "item_name": item.item_name,
                    "required_qty": item.qty,
                    "available_qty": available,
                    "shortage": shortage,
                    "status": "✅ OK" if sufficient else f"❌ Short by {shortage}"
                })
            
            recommendation = "Ready for delivery" if all_available else "Create Material Request for missing items"
            
            return {
                "success": True,
                "so_name": so.name,
                "link": self.make_link("Sales Order", so.name),
                "all_available": all_available,
                "recommendation": recommendation,
                "items": items
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_next_steps(self, so_name: str) -> Dict:
        """Recommend next actions based on current SO state"""
        try:
            so = frappe.get_doc("Sales Order", so_name)
            
            steps = []
            
            # Check status and provide guidance
            if so.docstatus == 0:
                steps.append("1. Submit the Sales Order to confirm it")
                return {
                    "success": True,
                    "so_name": so.name,
                    "link": self.make_link("Sales Order", so.name),
                    "status": "Draft",
                    "steps": steps
                }
            
            if so.status == "Completed":
                return {
                    "success": True,
                    "so_name": so.name,
                    "link": self.make_link("Sales Order", so.name),
                    "status": "Completed",
                    "steps": ["Order is fully completed - no actions needed"]
                }
            
            # Check inventory
            inv_check = self.check_inventory(so_name)
            
            if so.status in ["To Deliver and Bill", "To Deliver"]:
                if inv_check.get("all_available"):
                    steps.append("1. Create Delivery Note - inventory is available")
                    steps.append(f"   Use: Create > Delivery Note from {self.make_link('Sales Order', so.name)}")
                else:
                    steps.append("1. Create Material Request - inventory insufficient")
                    steps.append(f"   Use: Create > Material Request from {self.make_link('Sales Order', so.name)}")
                    
                    # Check for existing MR
                    mrs = frappe.get_all("Material Request Item",
                        filters={"sales_order": so_name, "docstatus": 1},
                        fields=["parent"], distinct=True)
                    
                    if mrs:
                        steps.append(f"   ⚠️ Existing MR found: {self.make_link('Material Request', mrs[0].parent)}")
                        
                        # Check for RFQ/PO
                        for mr in mrs:
                            rfqs = frappe.get_all("Request for Quotation Item",
                                filters={"material_request": mr.parent, "docstatus": 1},
                                fields=["parent"], distinct=True)
                            if rfqs:
                                steps.append(f"2. RFQ exists: {self.make_link('Request for Quotation', rfqs[0].parent)}")
                                
                                # Check for Supplier Quotations
                                sqs = frappe.get_all("Supplier Quotation",
                                    filters={"docstatus": 1},
                                    fields=["name"])
                                # Filter by RFQ link
                                for rfq in rfqs:
                                    linked_sqs = frappe.get_all("Supplier Quotation Item",
                                        filters={"request_for_quotation": rfq.parent, "docstatus": 1},
                                        fields=["parent"], distinct=True)
                                    if linked_sqs:
                                        steps.append(f"3. Supplier Quotation: {self.make_link('Supplier Quotation', linked_sqs[0].parent)}")
                                        steps.append("4. Create Purchase Order from Supplier Quotation")
                            else:
                                steps.append("2. Create RFQ from Material Request")
            
            if so.status in ["To Deliver and Bill", "To Bill"]:
                if so.delivery_status == "Fully Delivered":
                    steps.append(f"• Create Sales Invoice from {self.make_link('Sales Order', so.name)}")
            
            return {
                "success": True,
                "so_name": so.name,
                "link": self.make_link("Sales Order", so.name),
                "status": so.status,
                "delivery_status": so.delivery_status,
                "billing_status": so.billing_status,
                "inventory_available": inv_check.get("all_available", False),
                "steps": steps if steps else ["Review order status manually"]
            }
        except frappe.DoesNotExistError:
            return {"success": False, "error": f"Sales Order '{so_name}' not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== PURCHASE CYCLE TRACKING ==========
    
    def track_purchase_cycle(self, so_name: str) -> Dict:
        """Track the complete purchase cycle for a Sales Order"""
        try:
            so = frappe.get_doc("Sales Order", so_name)
            
            cycle = {
                "sales_order": {"name": so.name, "link": self.make_link("Sales Order", so.name), "status": so.status},
                "material_requests": [],
                "rfqs": [],
                "supplier_quotations": [],
                "purchase_orders": [],
                "purchase_receipts": []
            }
            
            # Get Material Requests
            mrs = frappe.get_all("Material Request Item",
                filters={"sales_order": so_name},
                fields=["parent"], distinct=True)
            
            for mr in mrs:
                mr_doc = frappe.get_doc("Material Request", mr.parent)
                cycle["material_requests"].append({
                    "name": mr_doc.name,
                    "link": self.make_link("Material Request", mr_doc.name),
                    "status": mr_doc.status,
                    "docstatus": mr_doc.docstatus
                })
                
                # Get RFQs from MR
                rfqs = frappe.get_all("Request for Quotation Item",
                    filters={"material_request": mr.parent},
                    fields=["parent"], distinct=True)
                
                for rfq in rfqs:
                    rfq_doc = frappe.get_doc("Request for Quotation", rfq.parent)
                    cycle["rfqs"].append({
                        "name": rfq_doc.name,
                        "link": self.make_link("Request for Quotation", rfq_doc.name),
                        "status": rfq_doc.status,
                        "docstatus": rfq_doc.docstatus
                    })
                    
                    # Get Supplier Quotations from RFQ
                    sqs = frappe.get_all("Supplier Quotation Item",
                        filters={"request_for_quotation": rfq.parent},
                        fields=["parent"], distinct=True)
                    
                    for sq in sqs:
                        sq_doc = frappe.get_doc("Supplier Quotation", sq.parent)
                        cycle["supplier_quotations"].append({
                            "name": sq_doc.name,
                            "link": self.make_link("Supplier Quotation", sq_doc.name),
                            "supplier": sq_doc.supplier,
                            "status": sq_doc.status,
                            "docstatus": sq_doc.docstatus
                        })
            
            # Get Purchase Orders linked to MRs
            for mr in mrs:
                pos = frappe.get_all("Purchase Order Item",
                    filters={"material_request": mr.parent},
                    fields=["parent"], distinct=True)
                
                for po in pos:
                    po_doc = frappe.get_doc("Purchase Order", po.parent)
                    if not any(p["name"] == po_doc.name for p in cycle["purchase_orders"]):
                        cycle["purchase_orders"].append({
                            "name": po_doc.name,
                            "link": self.make_link("Purchase Order", po_doc.name),
                            "supplier": po_doc.supplier,
                            "status": po_doc.status,
                            "docstatus": po_doc.docstatus
                        })
                        
                        # Get Purchase Receipts
                        prs = frappe.get_all("Purchase Receipt Item",
                            filters={"purchase_order": po.parent},
                            fields=["parent"], distinct=True)
                        
                        for pr in prs:
                            pr_doc = frappe.get_doc("Purchase Receipt", pr.parent)
                            if not any(p["name"] == pr_doc.name for p in cycle["purchase_receipts"]):
                                cycle["purchase_receipts"].append({
                                    "name": pr_doc.name,
                                    "link": self.make_link("Purchase Receipt", pr_doc.name),
                                    "status": pr_doc.status,
                                    "docstatus": pr_doc.docstatus
                                })
            
            return {"success": True, "cycle": cycle}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ========== MAIN HANDLER ==========
    
    def process_command(self, message: str) -> str:
        """Process incoming command and return response"""
        message_lower = message.lower().strip()
        
        # Extract SO name if present
        import re
        so_pattern = r'(SO-\d+-\w+|SAL-ORD-\d+-\d+)'
        so_match = re.search(so_pattern, message, re.IGNORECASE)
        so_name = so_match.group(1) if so_match else None
        
        # Route commands
        if "pending" in message_lower or "list" in message_lower:
            result = self.get_pending_orders()
            if result["success"]:
                lines = [f"## Pending Sales Orders ({result['count']} found)\n"]
                for order in result["orders"]:
                    lines.append(f"• {order['link']} | {order['customer']} | {order['status']}")
                    lines.append(f"  Delivery: {order['delivery_date']} | Total: {order['grand_total']}")
                    lines.append(f"  **Next:** {order['next_action']}\n")
                return "\n".join(lines)
            return f"❌ Error: {result['error']}"
        
        if so_name:
            if "inventory" in message_lower or "stock" in message_lower:
                result = self.check_inventory(so_name)
                if result["success"]:
                    lines = [f"## Inventory Check: {result['link']}\n"]
                    lines.append(f"**Overall:** {'✅ All items available' if result['all_available'] else '❌ Some items short'}\n")
                    for item in result["items"]:
                        lines.append(f"• {item['item_code']}: Need {item['required_qty']}, Have {item['available_qty']} → {item['status']}")
                    lines.append(f"\n**Recommendation:** {result['recommendation']}")
                    return "\n".join(lines)
                return f"❌ Error: {result['error']}"
            
            if "next" in message_lower or "step" in message_lower:
                result = self.get_next_steps(so_name)
                if result["success"]:
                    lines = [f"## Next Steps: {result['link']}\n"]
                    lines.append(f"**Status:** {result['status']}")
                    if result.get("delivery_status"):
                        lines.append(f"**Delivery:** {result['delivery_status']} | **Billing:** {result['billing_status']}")
                    lines.append("\n**Actions:**")
                    for step in result["steps"]:
                        lines.append(step)
                    return "\n".join(lines)
                return f"❌ Error: {result['error']}"
            
            if "track" in message_lower or "cycle" in message_lower:
                result = self.track_purchase_cycle(so_name)
                if result["success"]:
                    cycle = result["cycle"]
                    lines = [f"## Purchase Cycle: {cycle['sales_order']['link']}\n"]
                    lines.append(f"**SO Status:** {cycle['sales_order']['status']}\n")
                    
                    if cycle["material_requests"]:
                        lines.append("**Material Requests:**")
                        for mr in cycle["material_requests"]:
                            lines.append(f"  • {mr['link']} ({mr['status']})")
                    
                    if cycle["rfqs"]:
                        lines.append("\n**RFQs:**")
                        for rfq in cycle["rfqs"]:
                            lines.append(f"  • {rfq['link']} ({rfq['status']})")
                    
                    if cycle["supplier_quotations"]:
                        lines.append("\n**Supplier Quotations:**")
                        for sq in cycle["supplier_quotations"]:
                            lines.append(f"  • {sq['link']} - {sq['supplier']} ({sq['status']})")
                    
                    if cycle["purchase_orders"]:
                        lines.append("\n**Purchase Orders:**")
                        for po in cycle["purchase_orders"]:
                            lines.append(f"  • {po['link']} - {po['supplier']} ({po['status']})")
                    
                    if cycle["purchase_receipts"]:
                        lines.append("\n**Purchase Receipts:**")
                        for pr in cycle["purchase_receipts"]:
                            lines.append(f"  • {pr['link']} ({pr['status']})")
                    
                    return "\n".join(lines)
                return f"❌ Error: {result['error']}"
            
            # Default: show status
            result = self.get_so_status(so_name)
            if result["success"]:
                lines = [f"## Sales Order: {result['link']}\n"]
                lines.append(f"**Customer:** {result['customer']}")
                lines.append(f"**Status:** {result['status']}")
                lines.append(f"**Delivery:** {result['delivery_status']} | **Billing:** {result['billing_status']}")
                lines.append(f"**Total:** {result['grand_total']}")
                lines.append(f"**Delivery Date:** {result['delivery_date'] or 'Not set'}")
                lines.append(f"\n**Inventory:** {'✅ Sufficient' if result['inventory_sufficient'] else '❌ Insufficient'}")
                lines.append(f"**Next Action:** {result['next_action']}")
                
                docs = result["linked_documents"]
                if docs["delivery_notes"]:
                    lines.append(f"\n**Delivery Notes:** {', '.join(docs['delivery_notes'])}")
                if docs["sales_invoices"]:
                    lines.append(f"**Sales Invoices:** {', '.join(docs['sales_invoices'])}")
                if docs["material_requests"]:
                    lines.append(f"**Material Requests:** {', '.join(docs['material_requests'])}")
                
                return "\n".join(lines)
            return f"❌ Error: {result['error']}"
        
        # Help
        return """## Sales Order Follow-up Commands

**Check Status:**
• `status SO-XXXXX` - Detailed status of a Sales Order
• `pending` - List all pending Sales Orders

**Inventory & Next Steps:**
• `check inventory SO-XXXXX` - Check stock availability
• `next steps SO-XXXXX` - Recommended actions

**Purchase Cycle:**
• `track SO-XXXXX` - Track full purchase cycle (MR → RFQ → PO → Receipt)

**Workflow Reference:**
Opportunity → Quotation → **Sales Order** → Material Request → RFQ → Supplier Quotation → Purchase Order → Receive Goods → Deliver → Invoice
"""
