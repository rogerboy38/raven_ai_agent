"""
Executive Insights Agent
Multi-level business intelligence for managers via Raven chat.

Altitude Levels:
- 🚁 Helicopter: Company-wide KPIs
- 🐦 Bird: Department focus  
- 🐕 Dog: Exceptions & follow-ups
"""

import frappe
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class ExecutiveInsightsAgent:
    """Agent for executive-level business insights"""
    
    def __init__(self, user: str):
        self.user = user
        self.site_name = frappe.local.site
        
        # Model catalog - maps keywords to Insights models
        self.model_catalog = self._load_catalog()
    
    def _load_catalog(self) -> Dict:
        """Load the insights model catalog"""
        # This would ideally come from a DocType or JSON config
        return {
            "models": {
                # Funnel models
                "fact_leads": {
                    "altitude": "bird",
                    "department": "sales",
                    "keywords": ["leads", "prospectos", "lead source"],
                    "description": "Lead tracking and conversion"
                },
                "fact_opportunities": {
                    "altitude": "bird", 
                    "department": "sales",
                    "keywords": ["opportunities", "oportunidades", "pipeline", "deals"],
                    "description": "Sales pipeline and win rates"
                },
                "fact_quotations": {
                    "altitude": "bird",
                    "department": "sales", 
                    "keywords": ["quotations", "cotizaciones", "quotes"],
                    "description": "Quotation values and hit rates"
                },
                "fact_orders": {
                    "altitude": "bird",
                    "department": "sales",
                    "keywords": ["orders", "pedidos", "sales order", "revenue"],
                    "description": "Sales orders and fulfillment"
                },
                # Execution models
                "fact_work_orders": {
                    "altitude": "bird",
                    "department": "operations",
                    "keywords": ["work order", "produccion", "manufacturing", "production"],
                    "description": "Work order completion and lateness"
                },
                "fact_stock_position": {
                    "altitude": "bird",
                    "department": "operations",
                    "keywords": ["stock", "inventory", "inventario", "warehouse"],
                    "description": "Stock levels and availability"
                },
                "fact_deliveries": {
                    "altitude": "bird",
                    "department": "logistics",
                    "keywords": ["delivery", "entregas", "shipping", "otif"],
                    "description": "Delivery performance and OTIF"
                },
                "fact_invoices": {
                    "altitude": "bird",
                    "department": "finance",
                    "keywords": ["invoice", "factura", "billing", "revenue"],
                    "description": "Invoicing and DSO"
                },
                # Exception lists (Dog view)
                "list_overdue_orders": {
                    "altitude": "dog",
                    "department": "sales",
                    "keywords": ["overdue", "atrasado", "late orders", "stuck"],
                    "description": "Orders past delivery date"
                },
                "list_late_work_orders": {
                    "altitude": "dog",
                    "department": "operations",
                    "keywords": ["late production", "delayed wo", "work order late"],
                    "description": "Work orders behind schedule"
                },
                "list_stock_shortages": {
                    "altitude": "dog",
                    "department": "operations",
                    "keywords": ["shortage", "faltante", "stockout", "no stock"],
                    "description": "Items with insufficient stock"
                },
                "list_pending_invoices": {
                    "altitude": "dog",
                    "department": "finance",
                    "keywords": ["pending invoice", "not invoiced", "delivered not billed"],
                    "description": "Delivered but not invoiced"
                },
                # New models from Insights team spec
                "fact_order_items": {
                    "altitude": "bird",
                    "department": "sales",
                    "keywords": ["order items", "product mix", "line items"],
                    "description": "Line-item detail for product mix analysis"
                },
                "fact_shipments": {
                    "altitude": "bird",
                    "department": "logistics",
                    "keywords": ["shipments", "direct shipment", "transport"],
                    "description": "Logistics operations tracking"
                },
                "list_late_orders": {
                    "altitude": "dog",
                    "department": "sales",
                    "keywords": ["late orders", "overdue orders", "delayed"],
                    "description": "Exception list for overdue orders"
                }
            },
            "dashboards": {
                "executive_overview": {
                    "altitude": "helicopter",
                    "keywords": ["overview", "summary", "resumen", "general", "company"],
                    "url": "/insights/dashboard/executive_overview"
                },
                "sales_pipeline": {
                    "altitude": "bird",
                    "department": "sales",
                    "url": "/insights/dashboard/sales_pipeline"
                },
                "operations_monitor": {
                    "altitude": "bird",
                    "department": "operations",
                    "url": "/insights/dashboard/operations_monitor"
                }
            }
        }
    
    def process_command(self, query: str) -> str:
        """Main command processor"""
        query_lower = query.lower().strip()
        
        # Help command
        if query_lower in ["help", "ayuda", "?"]:
            return self._get_help()
        
        # Determine altitude and route
        if any(kw in query_lower for kw in ["summary", "overview", "resumen", "helicopter", "general", "company"]):
            return self._helicopter_view()
        
        if any(kw in query_lower for kw in ["alerts", "alertas", "exceptions", "dog", "follow up", "seguimiento", "pending", "stuck", "overdue"]):
            return self._dog_view(query_lower)
        
        # Department-specific (Bird view)
        if any(kw in query_lower for kw in ["sales", "ventas", "pipeline"]):
            return self._bird_view_sales()
        
        if any(kw in query_lower for kw in ["operations", "operaciones", "production", "produccion", "work order"]):
            return self._bird_view_operations()
        
        if any(kw in query_lower for kw in ["finance", "finanzas", "invoices", "facturas", "revenue"]):
            return self._bird_view_finance()
        
        if any(kw in query_lower for kw in ["logistics", "logistica", "delivery", "entregas", "shipping"]):
            return self._bird_view_logistics()
        
        # Default to helicopter view
        return self._helicopter_view()
    
    def _get_help(self) -> str:
        """Return help message"""
        return """## 📊 Executive Insights Agent

**Altitude Commands:**
| Command | View | Description |
|---------|------|-------------|
| `@executive summary` | 🚁 | Company-wide overview |
| `@executive sales` | 🐦 | Sales pipeline & orders |
| `@executive operations` | 🐦 | Work orders & production |
| `@executive finance` | 🐦 | Revenue & invoicing |
| `@executive logistics` | 🐦 | Deliveries & OTIF |
| `@executive alerts` | 🐕 | All exceptions |
| `@executive follow up` | 🐕 | What needs attention |

**Quick Questions:**
- "How are we doing?"
- "What's stuck?"
- "Show me the pipeline"
- "Any late orders?"
"""
    
    def _helicopter_view(self) -> str:
        """Company-wide KPI overview"""
        today = datetime.now()
        month_start = today.replace(day=1)
        
        try:
            # Revenue MTD
            revenue_mtd = frappe.db.sql("""
                SELECT COALESCE(SUM(grand_total), 0) as total
                FROM `tabSales Order`
                WHERE docstatus = 1
                  AND transaction_date >= %s
                  AND transaction_date <= %s
            """, (month_start, today), as_dict=True)[0].total or 0
            
            # Orders count MTD
            orders_count = frappe.db.count("Sales Order", {
                "docstatus": 1,
                "transaction_date": [">=", month_start],
                "transaction_date": ["<=", today]
            })
            
            # Open orders value
            open_orders = frappe.db.sql("""
                SELECT COALESCE(SUM(grand_total), 0) as total, COUNT(*) as count
                FROM `tabSales Order`
                WHERE docstatus = 1
                  AND status NOT IN ('Completed', 'Cancelled', 'Closed')
            """, as_dict=True)[0]
            
            # Work orders status
            wo_stats = frappe.db.sql("""
                SELECT status, COUNT(*) as count
                FROM `tabWork Order`
                WHERE docstatus < 2
                GROUP BY status
            """, as_dict=True)
            wo_summary = {r.status: r.count for r in wo_stats}
            
            # Overdue orders count
            overdue_count = frappe.db.sql("""
                SELECT COUNT(*) as count
                FROM `tabSales Order`
                WHERE docstatus = 1
                  AND status NOT IN ('Completed', 'Cancelled', 'Closed')
                  AND delivery_date < CURDATE()
            """, as_dict=True)[0].count or 0
            
            # Pending invoices (delivered not invoiced)
            pending_invoice_count = frappe.db.sql("""
                SELECT COUNT(DISTINCT dn.name) as count
                FROM `tabDelivery Note` dn
                LEFT JOIN `tabSales Invoice Item` sii ON sii.delivery_note = dn.name
                WHERE dn.docstatus = 1
                  AND sii.name IS NULL
            """, as_dict=True)[0].count or 0
            
            # Format response
            msg = f"""## 🚁 Executive Summary - {today.strftime('%B %Y')}

### 📊 Key Metrics
| Metric | Value |
|--------|-------|
| 💰 Revenue MTD | ${revenue_mtd:,.2f} |
| 📦 Orders MTD | {orders_count} |
| 📋 Open Orders | {open_orders.count} (${open_orders.total:,.2f}) |

### 🏭 Operations
| Status | Count |
|--------|-------|
"""
            for status, count in wo_summary.items():
                msg += f"| {status} | {count} |\n"
            
            msg += f"""
### ⚠️ Alerts
| Alert | Count |
|-------|-------|
| 🔴 Overdue Orders | {overdue_count} |
| 🟡 Pending Invoices | {pending_invoice_count} |

---
💡 Use `@executive alerts` for details | `@executive sales` for pipeline
"""
            return msg
            
        except Exception as e:
            frappe.logger().error(f"[Executive Agent] Helicopter view error: {str(e)}")
            return f"❌ Error generating executive summary: {str(e)}"
    
    def _dog_view(self, query: str = "") -> str:
        """Exception/follow-up view"""
        try:
            alerts = []
            
            # Overdue Sales Orders
            overdue_orders = frappe.db.sql("""
                SELECT name, customer, grand_total, delivery_date,
                       DATEDIFF(CURDATE(), delivery_date) as days_overdue
                FROM `tabSales Order`
                WHERE docstatus = 1
                  AND status NOT IN ('Completed', 'Cancelled', 'Closed')
                  AND delivery_date < CURDATE()
                ORDER BY days_overdue DESC
                LIMIT 10
            """, as_dict=True)
            
            if overdue_orders:
                alerts.append("### 🔴 Overdue Sales Orders\n")
                alerts.append("| Order | Customer | Days Late | Amount |\n|-------|----------|-----------|--------|\n")
                for o in overdue_orders:
                    link = f"[{o.name}](https://{self.site_name}/app/sales-order/{o.name})"
                    alerts.append(f"| {link} | {o.customer[:20]} | {o.days_overdue} | ${o.grand_total:,.0f} |\n")
            
            # Late Work Orders
            late_wo = frappe.db.sql("""
                SELECT name, production_item, qty, status, planned_end_date,
                       DATEDIFF(CURDATE(), planned_end_date) as days_late
                FROM `tabWork Order`
                WHERE docstatus = 1
                  AND status NOT IN ('Completed', 'Stopped', 'Cancelled')
                  AND planned_end_date < CURDATE()
                ORDER BY days_late DESC
                LIMIT 10
            """, as_dict=True)
            
            if late_wo:
                alerts.append("\n### 🟠 Late Work Orders\n")
                alerts.append("| Work Order | Item | Days Late | Qty |\n|------------|------|-----------|-----|\n")
                for w in late_wo:
                    link = f"[{w.name}](https://{self.site_name}/app/work-order/{w.name})"
                    alerts.append(f"| {link} | {w.production_item[:20]} | {w.days_late} | {w.qty} |\n")
            
            # Pending Quotations (no response > 7 days)
            stale_quotes = frappe.db.sql("""
                SELECT name, party_name, grand_total, transaction_date,
                       DATEDIFF(CURDATE(), transaction_date) as days_pending
                FROM `tabQuotation`
                WHERE docstatus = 1
                  AND status = 'Open'
                  AND transaction_date < DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                ORDER BY days_pending DESC
                LIMIT 10
            """, as_dict=True)
            
            if stale_quotes:
                alerts.append("\n### 🟡 Stale Quotations (>7 days)\n")
                alerts.append("| Quotation | Customer | Days | Amount |\n|-----------|----------|------|--------|\n")
                for q in stale_quotes:
                    link = f"[{q.name}](https://{self.site_name}/app/quotation/{q.name})"
                    alerts.append(f"| {link} | {q.party_name[:20]} | {q.days_pending} | ${q.grand_total:,.0f} |\n")
            
            if alerts:
                return "## 🐕 Follow-Up Required\n\n" + "".join(alerts)
            else:
                return "## ✅ All Clear!\n\nNo urgent items requiring follow-up."
                
        except Exception as e:
            frappe.logger().error(f"[Executive Agent] Dog view error: {str(e)}")
            return f"❌ Error: {str(e)}"
    
    def _bird_view_sales(self) -> str:
        """Sales department focus"""
        try:
            today = datetime.now()
            month_start = today.replace(day=1)
            
            # Pipeline summary
            pipeline = frappe.db.sql("""
                SELECT status, COUNT(*) as count, COALESCE(SUM(opportunity_amount), 0) as value
                FROM `tabOpportunity`
                WHERE status NOT IN ('Lost', 'Closed')
                GROUP BY status
            """, as_dict=True)
            
            # Quotations summary
            quotes = frappe.db.sql("""
                SELECT status, COUNT(*) as count, COALESCE(SUM(grand_total), 0) as value
                FROM `tabQuotation`
                WHERE docstatus < 2
                  AND transaction_date >= %s
                GROUP BY status
            """, (month_start,), as_dict=True)
            
            # Orders MTD
            orders = frappe.db.sql("""
                SELECT COUNT(*) as count, COALESCE(SUM(grand_total), 0) as value
                FROM `tabSales Order`
                WHERE docstatus = 1
                  AND transaction_date >= %s
            """, (month_start,), as_dict=True)[0]
            
            # Top customers
            top_customers = frappe.db.sql("""
                SELECT customer, SUM(grand_total) as total
                FROM `tabSales Order`
                WHERE docstatus = 1
                  AND transaction_date >= %s
                GROUP BY customer
                ORDER BY total DESC
                LIMIT 5
            """, (month_start,), as_dict=True)
            
            msg = f"""## 🐦 Sales Dashboard - {today.strftime('%B %Y')}

### 🎯 Pipeline
| Stage | Count | Value |
|-------|-------|-------|
"""
            for p in pipeline:
                msg += f"| {p.status} | {p.count} | ${p.value:,.0f} |\n"
            
            msg += f"""
### 📝 Quotations This Month
| Status | Count | Value |
|--------|-------|-------|
"""
            for q in quotes:
                msg += f"| {q.status} | {q.count} | ${q.value:,.0f} |\n"
            
            msg += f"""
### 📦 Orders MTD
- **Count**: {orders.count}
- **Value**: ${orders.value:,.2f}

### 🏆 Top Customers
"""
            for i, c in enumerate(top_customers, 1):
                msg += f"{i}. {c.customer}: ${c.total:,.0f}\n"
            
            return msg
            
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def _bird_view_operations(self) -> str:
        """Operations/Manufacturing focus"""
        try:
            # Work order status
            wo_status = frappe.db.sql("""
                SELECT status, COUNT(*) as count
                FROM `tabWork Order`
                WHERE docstatus < 2
                GROUP BY status
            """, as_dict=True)
            
            # Completion rate
            completion = frappe.db.sql("""
                SELECT 
                    COUNT(CASE WHEN status = 'Completed' THEN 1 END) as completed,
                    COUNT(*) as total
                FROM `tabWork Order`
                WHERE docstatus = 1
                  AND creation >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            """, as_dict=True)[0]
            completion_rate = (completion.completed / completion.total * 100) if completion.total > 0 else 0
            
            # Active work orders
            active_wo = frappe.db.sql("""
                SELECT name, production_item, qty, produced_qty, status, planned_end_date
                FROM `tabWork Order`
                WHERE docstatus = 1
                  AND status IN ('Not Started', 'In Process')
                ORDER BY planned_end_date
                LIMIT 10
            """, as_dict=True)
            
            msg = f"""## 🐦 Operations Dashboard

### 📊 Work Order Status
| Status | Count |
|--------|-------|
"""
            for s in wo_status:
                msg += f"| {s.status} | {s.count} |\n"
            
            msg += f"""
### 📈 30-Day Performance
- **Completion Rate**: {completion_rate:.1f}%
- **Completed**: {completion.completed} / {completion.total}

### 🏭 Active Work Orders
| Work Order | Item | Progress | Due Date |
|------------|------|----------|----------|
"""
            for w in active_wo:
                link = f"[{w.name}](https://{self.site_name}/app/work-order/{w.name})"
                progress = f"{w.produced_qty or 0}/{w.qty}"
                due = str(w.planned_end_date) if w.planned_end_date else "—"
                msg += f"| {link} | {w.production_item[:15]} | {progress} | {due} |\n"
            
            return msg
            
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def _bird_view_finance(self) -> str:
        """Finance focus"""
        try:
            today = datetime.now()
            month_start = today.replace(day=1)
            
            # Revenue MTD (from invoices)
            revenue = frappe.db.sql("""
                SELECT COALESCE(SUM(grand_total), 0) as total, COUNT(*) as count
                FROM `tabSales Invoice`
                WHERE docstatus = 1
                  AND posting_date >= %s
            """, (month_start,), as_dict=True)[0]
            
            # Outstanding receivables
            receivables = frappe.db.sql("""
                SELECT COALESCE(SUM(outstanding_amount), 0) as total
                FROM `tabSales Invoice`
                WHERE docstatus = 1
                  AND outstanding_amount > 0
            """, as_dict=True)[0].total or 0
            
            # Outstanding payables
            payables = frappe.db.sql("""
                SELECT COALESCE(SUM(outstanding_amount), 0) as total
                FROM `tabPurchase Invoice`
                WHERE docstatus = 1
                  AND outstanding_amount > 0
            """, as_dict=True)[0].total or 0
            
            msg = f"""## 🐦 Finance Dashboard - {today.strftime('%B %Y')}

### 💰 Revenue MTD
- **Invoiced**: ${revenue.total:,.2f}
- **Invoice Count**: {revenue.count}

### 📊 Cash Position
| Category | Amount |
|----------|--------|
| 📥 Receivables | ${receivables:,.2f} |
| 📤 Payables | ${payables:,.2f} |
| 💵 Net | ${(receivables - payables):,.2f} |
"""
            return msg
            
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def _bird_view_logistics(self) -> str:
        """Logistics/Delivery focus"""
        try:
            today = datetime.now()
            month_start = today.replace(day=1)
            
            # Deliveries this month
            deliveries = frappe.db.sql("""
                SELECT COUNT(*) as count, COALESCE(SUM(grand_total), 0) as value
                FROM `tabDelivery Note`
                WHERE docstatus = 1
                  AND posting_date >= %s
            """, (month_start,), as_dict=True)[0]
            
            # Pending deliveries
            pending = frappe.db.sql("""
                SELECT so.name, so.customer, so.delivery_date,
                       DATEDIFF(so.delivery_date, CURDATE()) as days_until
                FROM `tabSales Order` so
                WHERE so.docstatus = 1
                  AND so.status NOT IN ('Completed', 'Cancelled', 'Closed')
                  AND so.per_delivered < 100
                ORDER BY so.delivery_date
                LIMIT 10
            """, as_dict=True)
            
            msg = f"""## 🐦 Logistics Dashboard - {today.strftime('%B %Y')}

### 🚚 Deliveries MTD
- **Count**: {deliveries.count}
- **Value**: ${deliveries.value:,.2f}

### 📦 Pending Deliveries
| Order | Customer | Due Date | Days |
|-------|----------|----------|------|
"""
            for p in pending:
                link = f"[{p.name}](https://{self.site_name}/app/sales-order/{p.name})"
                days = f"{p.days_until}" if p.days_until >= 0 else f"⚠️ {abs(p.days_until)} late"
                msg += f"| {link} | {p.customer[:15]} | {p.delivery_date} | {days} |\n"
            
            return msg
            
        except Exception as e:
            return f"❌ Error: {str(e)}"


# API Functions
def get_executive_summary(user: str = None) -> Dict:
    """Get executive summary data"""
    agent = ExecutiveInsightsAgent(user or frappe.session.user)
    return {"message": agent._helicopter_view()}


def get_alerts(user: str = None) -> Dict:
    """Get alerts/exceptions"""
    agent = ExecutiveInsightsAgent(user or frappe.session.user)
    return {"message": agent._dog_view()}


# Alias for compatibility with agent.py import
ExecutiveAgent = ExecutiveInsightsAgent
