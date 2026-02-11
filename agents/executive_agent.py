"""
Executive Insights Agent
Multi-level business intelligence for managers via Raven chat.

Altitude Levels:
- 🚁 Helicopter: Company-wide KPIs
- 🐦 Bird: Department focus  
- 🐕 Dog: Exceptions & follow-ups

Data Source: Frappe Insights (raven_ai_agent_sales_kpi workbook)
"""

import frappe
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any


class ExecutiveInsightsAgent:
    """Agent for executive-level business insights"""
    
    # Insights query mapping - all queries in raven_ai_agent_sales_kpi workbook
    INSIGHTS_QUERIES = {
        # KPIs (Helicopter)
        "kpi_revenue_mtd": "kpi_revenue_mtd",
        "kpi_fulfillment_rate": "kpi_fulfillment_rate",
        "kpi_avg_cycle_time": "kpi_avg_cycle_time",
        "kpi_wo_completion_rate": "kpi_wo_completion_rate",
        # Fact tables (Bird)
        "fact_orders": "fact_orders",
        "fact_deliveries": "fact_deliveries",
        "fact_stock_position": "fact_stock_position",
        "fact_work_orders": "fact_work_orders",
        # Lists (Dog)
        "list_late_orders": "list_late_orders",
        "list_pending_deliveries": "list_pending_deliveries",
        "list_low_stock": "list_low_stock",
        "list_late_work_orders": "list_late_work_orders",
        # Sales
        "top_customers_mtd": "top_customers_mtd",
        "pipeline_summary": "pipeline_summary",
    }
    
    def __init__(self, user: str):
        self.user = user
        self.site_name = frappe.local.site
        self.use_insights = self._check_insights_available()
    
    def _check_insights_available(self) -> bool:
        """Check if Frappe Insights is available"""
        try:
            return frappe.db.exists("Insights Query", {"name": ["like", "%revenue%"]})
        except:
            return False
    
    def _query_insights(self, query_name: str) -> List[Dict]:
        """Query Frappe Insights model"""
        try:
            # Try Insights API first
            if self.use_insights:
                result = frappe.call(
                    "insights.api.queries.get_query_result",
                    query_name=self.INSIGHTS_QUERIES.get(query_name, query_name)
                )
                if result and "result" in result:
                    return result["result"]
            return []
        except Exception as e:
            frappe.logger().warning(f"[Executive Agent] Insights query failed: {e}")
            return []
    
    def _query_direct(self, sql: str, values: tuple = None) -> List[Dict]:
        """Direct SQL fallback"""
        try:
            return frappe.db.sql(sql, values, as_dict=True)
        except Exception as e:
            frappe.logger().error(f"[Executive Agent] SQL error: {e}")
            return []
    
    def process_command(self, query: str) -> str:
        """Main command processor"""
        query_lower = query.lower().strip()
        
        if query_lower in ["help", "ayuda", "?"]:
            return self._get_help()
        
        if any(kw in query_lower for kw in ["summary", "overview", "resumen", "helicopter", "general", "company"]):
            return self._helicopter_view()
        
        if any(kw in query_lower for kw in ["alerts", "alertas", "exceptions", "dog", "follow up", "seguimiento", "pending", "stuck", "overdue"]):
            return self._dog_view(query_lower)
        
        if any(kw in query_lower for kw in ["sales", "ventas", "pipeline"]):
            return self._bird_view_sales()
        
        if any(kw in query_lower for kw in ["operations", "operaciones", "production", "produccion", "work order"]):
            return self._bird_view_operations()
        
        if any(kw in query_lower for kw in ["finance", "finanzas", "invoices", "facturas", "revenue"]):
            return self._bird_view_finance()
        
        if any(kw in query_lower for kw in ["logistics", "logistica", "delivery", "entregas", "shipping"]):
            return self._bird_view_logistics()
        
        return self._helicopter_view()
    
    def _get_help(self) -> str:
        """Return help message"""
        return """## 📊 Executive Insights Agent

| Command | View | Description |
|---------|------|-------------|
| `@executive summary` | 🚁 | Company-wide overview |
| `@executive sales` | 🐦 | Sales pipeline & orders |
| `@executive operations` | 🐦 | Work orders & production |
| `@executive finance` | 🐦 | Revenue & invoicing |
| `@executive logistics` | 🐦 | Deliveries & OTIF |
| `@executive alerts` | 🐕 | All exceptions |

**Quick Questions:** "How are we doing?" · "What's stuck?" · "Any late orders?"
"""
    
    def _helicopter_view(self) -> str:
        """Company-wide KPI overview - Executive Summary"""
        today = datetime.now()
        month_start = today.replace(day=1)
        
        try:
            # Try Insights KPIs first, fallback to direct SQL
            revenue_mtd = self._get_kpi_revenue_mtd(month_start, today)
            orders_mtd = self._get_orders_mtd(month_start, today)
            open_orders = self._get_open_orders()
            fulfillment_rate = self._get_fulfillment_rate()
            cycle_time = self._get_avg_cycle_time()
            
            # Alerts counts
            overdue_count = self._get_overdue_count()
            pending_invoice_count = self._get_pending_invoice_count()
            low_stock_count = self._get_low_stock_count()
            
            # Work order summary
            wo_summary = self._get_wo_summary()
            
            # Format fulfillment status indicator
            fulf_status = "🟢" if fulfillment_rate >= 80 else "🟡" if fulfillment_rate >= 50 else "🔴"
            cycle_status = "🟢" if cycle_time <= 14 else "🟡" if cycle_time <= 21 else "🔴"
            
            msg = f"""## 🚁 Executive Summary
### {today.strftime('%B %d, %Y')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 📊 Key Metrics (Month-to-Date)

| Metric | Value | Status |
|--------|-------|--------|
| 💰 Revenue MTD | ${revenue_mtd:,.2f} | - |
| 📦 Orders MTD | {orders_mtd['count']} | ${orders_mtd['value']:,.2f} |
| 📋 Open Orders | {open_orders['count']} | ${open_orders['value']:,.2f} |
| ✅ Fulfillment Rate | {fulfillment_rate:.1f}% | {fulf_status} |
| ⏱️ Avg Cycle Time | {cycle_time:.1f} days | {cycle_status} |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 🏭 Work Order Status

| Status | Count |
|--------|-------|
"""
            for status, count in wo_summary.items():
                emoji = "🟢" if status == "Completed" else "🔵" if status == "In Process" else "⚪"
                msg += f"| {emoji} {status} | {count} |\n"
            
            # Alerts section
            total_alerts = overdue_count + pending_invoice_count + low_stock_count
            alert_indicator = "🔴" if total_alerts > 10 else "🟡" if total_alerts > 0 else "🟢"
            
            msg += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### ⚠️ Alerts Requiring Attention {alert_indicator}

| Alert Type | Count | Action |
|------------|-------|--------|
| 🔴 Late Orders | {overdue_count} | {"Follow up needed" if overdue_count > 0 else "✓ Clear"} |
| 🟡 Pending Invoices | {pending_invoice_count} | {"Bill deliveries" if pending_invoice_count > 0 else "✓ Clear"} |
| 🟠 Low Stock Items | {low_stock_count} | {"Check inventory" if low_stock_count > 0 else "✓ Clear"} |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 **Next Steps:** `@executive alerts` for details · `@executive sales` for pipeline
"""
            return msg
            
        except Exception as e:
            frappe.logger().error(f"[Executive Agent] Helicopter view error: {str(e)}")
            return f"❌ Error generating executive summary: {str(e)}"
    
    # ─────────────────────────────────────────────────────────────────
    # KPI Helper Methods (with Insights fallback)
    # ─────────────────────────────────────────────────────────────────
    
    def _get_kpi_revenue_mtd(self, month_start, today) -> float:
        """Get revenue MTD from Insights or direct SQL"""
        # Try Insights first
        result = self._query_insights("kpi_revenue_mtd")
        if result and len(result) > 0:
            return float(result[0].get("revenue_mtd", 0) or 0)
        
        # Fallback to direct SQL
        data = self._query_direct("""
            SELECT COALESCE(SUM(grand_total), 0) as total
            FROM `tabSales Order`
            WHERE docstatus = 1 AND transaction_date >= %s AND transaction_date <= %s
        """, (month_start, today))
        return float(data[0].total if data else 0)
    
    def _get_orders_mtd(self, month_start, today) -> Dict:
        """Get orders count and value MTD"""
        # Try Insights fact_orders
        result = self._query_insights("fact_orders")
        if result:
            count = len([r for r in result if r.get("transaction_date", "") >= str(month_start.date())])
            value = sum(float(r.get("grand_total", 0) or 0) for r in result 
                       if r.get("transaction_date", "") >= str(month_start.date()))
            if count > 0:
                return {"count": count, "value": value}
        
        # Fallback
        data = self._query_direct("""
            SELECT COUNT(*) as count, COALESCE(SUM(grand_total), 0) as value
            FROM `tabSales Order`
            WHERE docstatus = 1 AND transaction_date >= %s AND transaction_date <= %s
        """, (month_start, today))
        return {"count": data[0].count if data else 0, "value": float(data[0].value if data else 0)}
    
    def _get_open_orders(self) -> Dict:
        """Get open orders count and value"""
        data = self._query_direct("""
            SELECT COUNT(*) as count, COALESCE(SUM(grand_total), 0) as value
            FROM `tabSales Order`
            WHERE docstatus = 1 AND status NOT IN ('Completed', 'Cancelled', 'Closed')
        """)
        return {"count": data[0].count if data else 0, "value": float(data[0].value if data else 0)}
    
    def _get_fulfillment_rate(self) -> float:
        """Get fulfillment rate from Insights or calculate"""
        result = self._query_insights("kpi_fulfillment_rate")
        if result and len(result) > 0:
            return float(result[0].get("fulfillment_rate", 0) or 0)
        
        data = self._query_direct("""
            SELECT 
                COUNT(CASE WHEN per_delivered >= 100 THEN 1 END) as delivered,
                COUNT(*) as total
            FROM `tabSales Order`
            WHERE docstatus = 1 AND status NOT IN ('Cancelled')
        """)
        if data and data[0].total > 0:
            return (data[0].delivered / data[0].total) * 100
        return 0.0
    
    def _get_avg_cycle_time(self) -> float:
        """Get average order-to-delivery cycle time"""
        result = self._query_insights("kpi_avg_cycle_time")
        if result and len(result) > 0:
            return float(result[0].get("avg_cycle_time", 0) or 0)
        
        data = self._query_direct("""
            SELECT AVG(DATEDIFF(dn.posting_date, so.transaction_date)) as avg_days
            FROM `tabDelivery Note` dn
            JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
            JOIN `tabSales Order` so ON dni.against_sales_order = so.name
            WHERE dn.docstatus = 1 AND dn.posting_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)
        """)
        return float(data[0].avg_days or 0) if data else 0.0
    
    def _get_overdue_count(self) -> int:
        """Get count of overdue orders"""
        result = self._query_insights("list_late_orders")
        if result:
            return len(result)
        
        data = self._query_direct("""
            SELECT COUNT(*) as count FROM `tabSales Order`
            WHERE docstatus = 1 AND status NOT IN ('Completed', 'Cancelled', 'Closed')
            AND delivery_date < CURDATE()
        """)
        return data[0].count if data else 0
    
    def _get_pending_invoice_count(self) -> int:
        """Get count of delivered but not invoiced"""
        result = self._query_insights("list_pending_deliveries")
        if result:
            return len(result)
        
        data = self._query_direct("""
            SELECT COUNT(DISTINCT dn.name) as count
            FROM `tabDelivery Note` dn
            LEFT JOIN `tabSales Invoice Item` sii ON sii.delivery_note = dn.name
            WHERE dn.docstatus = 1 AND sii.name IS NULL
        """)
        return data[0].count if data else 0
    
    def _get_low_stock_count(self) -> int:
        """Get count of low stock items"""
        result = self._query_insights("list_low_stock")
        if result:
            return len(result)
        return 0  # No fallback for this one
    
    def _get_wo_summary(self) -> Dict[str, int]:
        """Get work order status summary"""
        data = self._query_direct("""
            SELECT status, COUNT(*) as count
            FROM `tabWork Order` WHERE docstatus < 2 GROUP BY status
        """)
        return {r.status: r.count for r in data} if data else {}
    
    # ─────────────────────────────────────────────────────────────────
    # Dog View (Alerts/Exceptions)
    # ─────────────────────────────────────────────────────────────────
    
    def _dog_view(self, query: str = "") -> str:
        """Exception/follow-up view with detailed lists"""
        try:
            sections = []
            
            # Late Orders from Insights or SQL
            late_orders = self._query_insights("list_late_orders")
            if not late_orders:
                late_orders = self._query_direct("""
                    SELECT name, customer, grand_total, delivery_date,
                           DATEDIFF(CURDATE(), delivery_date) as days_overdue
                    FROM `tabSales Order`
                    WHERE docstatus = 1 AND status NOT IN ('Completed', 'Cancelled', 'Closed')
                    AND delivery_date < CURDATE()
                    ORDER BY days_overdue DESC LIMIT 10
                """)
            
            if late_orders:
                sections.append("### 🔴 Late Orders\n")
                sections.append("| Order | Customer | Amount | Days Late |")
                sections.append("|-------|----------|--------|-----------|")
                for o in late_orders[:10]:
                    name = o.get("name", o.get("order_id", ""))
                    customer = str(o.get("customer", ""))[:20]
                    amount = float(o.get("grand_total", 0) or 0)
                    days = o.get("days_overdue", o.get("days_late", 0))
                    link = f"[{name}](https://{self.site_name}/app/sales-order/{name})"
                    sections.append(f"| {link} | {customer} | ${amount:,.0f} | {days} days |")
                sections.append("")
            
            # Pending Deliveries
            pending_del = self._query_insights("list_pending_deliveries")
            if not pending_del:
                pending_del = self._query_direct("""
                    SELECT dn.name, dn.customer, dn.grand_total, dn.posting_date,
                           DATEDIFF(CURDATE(), dn.posting_date) as days_pending
                    FROM `tabDelivery Note` dn
                    LEFT JOIN `tabSales Invoice Item` sii ON sii.delivery_note = dn.name
                    WHERE dn.docstatus = 1 AND sii.name IS NULL
                    ORDER BY days_pending DESC LIMIT 10
                """)
            
            if pending_del:
                sections.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                sections.append("### 🟡 Pending Invoices (Delivered Not Billed)\n")
                sections.append("| Delivery Note | Customer | Amount | Days Pending |")
                sections.append("|---------------|----------|--------|--------------|")
                for d in pending_del[:10]:
                    name = d.get("name", "")
                    customer = str(d.get("customer", ""))[:20]
                    amount = float(d.get("grand_total", 0) or 0)
                    days = d.get("days_pending", 0)
                    link = f"[{name}](https://{self.site_name}/app/delivery-note/{name})"
                    sections.append(f"| {link} | {customer} | ${amount:,.0f} | {days} days |")
                sections.append("")
            
            # Low Stock Items
            low_stock = self._query_insights("list_low_stock")
            if low_stock:
                sections.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                sections.append("### 🟠 Low Stock Items\n")
                sections.append("| Item | Warehouse | Qty | Threshold |")
                sections.append("|------|-----------|-----|-----------|")
                for s in low_stock[:10]:
                    item = str(s.get("item_code", ""))[:20]
                    warehouse = str(s.get("warehouse", ""))[:15]
                    qty = s.get("actual_qty", s.get("qty", 0))
                    threshold = s.get("threshold", s.get("reorder_level", "-"))
                    sections.append(f"| {item} | {warehouse} | {qty} | {threshold} |")
                sections.append("")
            
            # Late Work Orders
            late_wo = self._query_insights("list_late_work_orders")
            if not late_wo:
                late_wo = self._query_direct("""
                    SELECT name, production_item, qty, status, planned_end_date,
                           DATEDIFF(CURDATE(), planned_end_date) as days_late
                    FROM `tabWork Order`
                    WHERE docstatus = 1 AND status NOT IN ('Completed', 'Stopped', 'Cancelled')
                    AND planned_end_date < CURDATE()
                    ORDER BY days_late DESC LIMIT 10
                """)
            
            if late_wo:
                sections.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                sections.append("### 🟣 Late Work Orders\n")
                sections.append("| Work Order | Item | Status | Days Late |")
                sections.append("|------------|------|--------|-----------|")
                for w in late_wo[:10]:
                    name = w.get("name", "")
                    item = str(w.get("production_item", ""))[:15]
                    status = w.get("status", "")
                    days = w.get("days_late", 0)
                    link = f"[{name}](https://{self.site_name}/app/work-order/{name})"
                    sections.append(f"| {link} | {item} | {status} | {days} days |")
                sections.append("")
            
            # Stale Quotations (>7 days without response)
            stale_quotes = self._query_direct("""
                SELECT name, party_name, grand_total, transaction_date,
                       DATEDIFF(CURDATE(), transaction_date) as days_pending
                FROM `tabQuotation`
                WHERE docstatus = 1 AND status = 'Open'
                AND transaction_date < DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                ORDER BY days_pending DESC LIMIT 10
            """)
            
            if stale_quotes:
                sections.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
                sections.append("### 🟡 Stale Quotations (>7 days)\n")
                sections.append("| Quotation | Customer | Amount | Days |")
                sections.append("|-----------|----------|--------|------|")
                for q in stale_quotes[:10]:
                    name = q.get("name", "")
                    customer = str(q.get("party_name", ""))[:20]
                    amount = float(q.get("grand_total", 0) or 0)
                    days = q.get("days_pending", 0)
                    link = f"[{name}](https://{self.site_name}/app/quotation/{name})"
                    sections.append(f"| {link} | {customer} | ${amount:,.0f} | {days} |")
                sections.append("")
            
            if sections:
                header = "## 🐕 Follow-Up Required\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                footer = "\n\n💡 Click links to open in ERPNext"
                return header + "\n".join(sections) + footer
            else:
                return "## ✅ All Clear!\n\n🎉 No urgent items requiring follow-up."
                
        except Exception as e:
            frappe.logger().error(f"[Executive Agent] Dog view error: {str(e)}")
            return f"❌ Error: {str(e)}"
    
    # ─────────────────────────────────────────────────────────────────
    # Bird Views (Department Focus)
    # ─────────────────────────────────────────────────────────────────
    
    def _bird_view_sales(self) -> str:
        """Sales department focus"""
        try:
            today = datetime.now()
            month_start = today.replace(day=1)
            
            # Pipeline from Insights or SQL fallback
            pipeline = self._query_insights("pipeline_summary")
            if not pipeline:
                pipeline = self._query_direct("""
                    SELECT status, COUNT(*) as count, COALESCE(SUM(opportunity_amount), 0) as value
                    FROM `tabOpportunity` WHERE status NOT IN ('Lost', 'Closed') GROUP BY status
                """)
            
            # Quotations
            quotes = self._query_direct("""
                SELECT status, COUNT(*) as count, COALESCE(SUM(grand_total), 0) as value
                FROM `tabQuotation` WHERE docstatus < 2 AND transaction_date >= %s GROUP BY status
            """, (month_start,))
            
            # Orders MTD
            orders = self._get_orders_mtd(month_start, today)
            
            # Top customers from Insights or SQL fallback
            top_customers = self._query_insights("top_customers_mtd")
            if not top_customers:
                top_customers = self._query_direct("""
                    SELECT customer, SUM(grand_total) as total
                    FROM `tabSales Order` WHERE docstatus = 1 AND transaction_date >= %s
                    GROUP BY customer ORDER BY total DESC LIMIT 5
                """, (month_start,))
            
            # Calculate totals - handle both Insights and SQL field names
            def get_value(p): return float(p.get("total_value", p.get("value", 0)) or 0)
            def get_count(p): return int(p.get("opportunity_count", p.get("count", 0)) or 0)
            
            pipeline_total = sum(get_value(p) for p in pipeline)
            quote_total = sum(float(q.get("value", 0) or 0) for q in quotes)
            
            msg = f"""## 🐦 Sales Dashboard
### {today.strftime('%B %Y')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 🎯 Pipeline Overview

| Stage | Deals | Value | % of Total |
|-------|-------|-------|------------|
"""
            for p in pipeline:
                val = get_value(p)
                cnt = get_count(p)
                status = p.get("status", "Unknown")
                pct = (val / pipeline_total * 100) if pipeline_total > 0 else 0
                emoji = "🟢" if status == "Converted" else "🔵" if status == "Open" else "🟡"
                msg += f"| {emoji} {status} | {cnt} | ${val:,.0f} | {pct:.1f}% |\n"
            msg += f"| **Total** | **{sum(get_count(p) for p in pipeline)}** | **${pipeline_total:,.0f}** | - |\n"
            
            msg += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 📝 Quotations (This Month)

| Status | Count | Value | % of Total |
|--------|-------|-------|------------|
"""
            for q in quotes:
                pct = (float(q.value or 0) / quote_total * 100) if quote_total > 0 else 0
                msg += f"| {q.status} | {q.count} | ${float(q.value or 0):,.0f} | {pct:.1f}% |\n"
            
            avg_order = orders['value'] / orders['count'] if orders['count'] > 0 else 0
            msg += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 📦 Orders MTD Summary

| Metric | Value |
|--------|-------|
| Total Orders | {orders['count']} |
| Total Value | ${orders['value']:,.2f} |
| Avg Order Value | ${avg_order:,.0f} |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 🏆 Top Customers (by Revenue)

| Rank | Customer | Revenue |
|------|----------|---------|
"""
            for i, c in enumerate(top_customers, 1):
                # Handle both Insights (revenue_mtd, customer_name) and SQL (total, customer) field names
                cust_name = str(c.get("customer_name", c.get("customer", "")))[:25]
                revenue = float(c.get("revenue_mtd", c.get("total", 0)) or 0)
                msg += f"| {i} | {cust_name} | ${revenue:,.0f} |\n"
            
            msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            msg += "💡 **Drill down:** `@executive alerts` → late orders"
            
            return msg
            
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def _bird_view_operations(self) -> str:
        """Operations/Manufacturing focus"""
        try:
            # Get work orders from Insights or SQL
            work_orders = self._query_insights("fact_work_orders")
            if work_orders:
                # Build status summary from Insights data
                status_counts = {}
                for wo in work_orders:
                    status = wo.get("status", "Unknown")
                    status_counts[status] = status_counts.get(status, 0) + 1
                wo_status = [{"status": k, "count": v} for k, v in status_counts.items()]
                active_wo = [wo for wo in work_orders if wo.get("status") in ("Not Started", "In Process")][:10]
            else:
                wo_status = self._query_direct("""
                    SELECT status, COUNT(*) as count FROM `tabWork Order` WHERE docstatus < 2 GROUP BY status
                """)
                active_wo = self._query_direct("""
                    SELECT name, production_item, qty, produced_qty, status, planned_end_date
                    FROM `tabWork Order` WHERE docstatus = 1 AND status IN ('Not Started', 'In Process')
                    ORDER BY planned_end_date LIMIT 10
                """)
            
            # Get completion rate from Insights or calculate
            kpi_result = self._query_insights("kpi_wo_completion_rate")
            if kpi_result and kpi_result[0].get("completion_rate") is not None:
                completion_rate = float(kpi_result[0].get("completion_rate", 0) or 0)
                completed = kpi_result[0].get("completed_count", 0)
                total = kpi_result[0].get("total_count", 0)
            else:
                completion = self._query_direct("""
                    SELECT COUNT(CASE WHEN status = 'Completed' THEN 1 END) as completed, COUNT(*) as total
                    FROM `tabWork Order` WHERE docstatus = 1 AND creation >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                """)
                completion_rate = (completion[0].completed / completion[0].total * 100) if completion and completion[0].total > 0 else 0
                completed = completion[0].completed if completion else 0
                total = completion[0].total if completion else 0
            
            msg = f"""## 🐦 Operations Dashboard

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 📊 Work Order Status

| Status | Count | % of Total |
|--------|-------|------------|
"""
            # Handle both dict and object formats
            def get_attr(obj, key, default=0):
                return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)
            
            total_wo = sum(get_attr(s, "count", 0) for s in wo_status) if wo_status else 0
            for s in wo_status:
                cnt = get_attr(s, "count", 0)
                status = get_attr(s, "status", "Unknown")
                pct = (cnt / total_wo * 100) if total_wo > 0 else 0
                emoji = "🟢" if status == "Completed" else "🔵" if status == "In Process" else "⚪"
                msg += f"| {emoji} {status} | {cnt} | {pct:.1f}% |\n"
            
            rate_status = "🟢" if completion_rate >= 80 else "🟡" if completion_rate >= 50 else "🔴"
            msg += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 📈 30-Day Performance

| Metric | Value | Status |
|--------|-------|--------|
| Completion Rate | {completion_rate:.1f}% | {rate_status} |
| Completed | {completed} | - |
| Total | {total} | - |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 🏭 Active Work Orders

| Work Order | Item | Progress | Due Date |
|------------|------|----------|----------|
"""
            for w in active_wo:
                wo_name = get_attr(w, "name", "")
                prod_item = str(get_attr(w, "production_item", ""))[:15]
                produced = get_attr(w, "produced_qty", 0) or 0
                qty = get_attr(w, "qty", 0)
                due_date = get_attr(w, "planned_end_date", None)
                link = f"[{wo_name}](https://{self.site_name}/app/work-order/{wo_name})"
                progress = f"{produced}/{qty}"
                due = str(due_date) if due_date else "—"
                msg += f"| {link} | {prod_item} | {progress} | {due} |\n"
            
            return msg
            
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def _bird_view_finance(self) -> str:
        """Finance focus"""
        try:
            today = datetime.now()
            month_start = today.replace(day=1)
            
            revenue = self._query_direct("""
                SELECT COALESCE(SUM(grand_total), 0) as total, COUNT(*) as count
                FROM `tabSales Invoice` WHERE docstatus = 1 AND posting_date >= %s
            """, (month_start,))
            
            receivables = self._query_direct("""
                SELECT COALESCE(SUM(outstanding_amount), 0) as total
                FROM `tabSales Invoice` WHERE docstatus = 1 AND outstanding_amount > 0
            """)
            
            payables = self._query_direct("""
                SELECT COALESCE(SUM(outstanding_amount), 0) as total
                FROM `tabPurchase Invoice` WHERE docstatus = 1 AND outstanding_amount > 0
            """)
            
            recv = float(receivables[0].total if receivables else 0)
            pay = float(payables[0].total if payables else 0)
            net = recv - pay
            net_status = "🟢" if net > 0 else "🔴"
            
            msg = f"""## 🐦 Finance Dashboard
### {today.strftime('%B %Y')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 💰 Revenue MTD

| Metric | Value |
|--------|-------|
| Invoiced | ${float(revenue[0].total if revenue else 0):,.2f} |
| Invoice Count | {revenue[0].count if revenue else 0} |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 📊 Cash Position

| Category | Amount | Status |
|----------|--------|--------|
| 📥 Receivables | ${recv:,.2f} | - |
| 📤 Payables | ${pay:,.2f} | - |
| 💵 Net Position | ${net:,.2f} | {net_status} |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 **Next:** `@executive alerts` → pending invoices
"""
            return msg
            
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def _bird_view_logistics(self) -> str:
        """Logistics/Delivery focus"""
        try:
            today = datetime.now()
            month_start = today.replace(day=1)
            
            # Deliveries from Insights or SQL
            deliveries = self._query_insights("fact_deliveries")
            if not deliveries:
                deliveries = self._query_direct("""
                    SELECT COUNT(*) as count, COALESCE(SUM(grand_total), 0) as value
                    FROM `tabDelivery Note` WHERE docstatus = 1 AND posting_date >= %s
                """, (month_start,))
                del_count = deliveries[0].count if deliveries else 0
                del_value = float(deliveries[0].value if deliveries else 0)
            else:
                del_count = len(deliveries)
                del_value = sum(float(d.get("grand_total", 0) or 0) for d in deliveries)
            
            # Pending deliveries
            pending = self._query_direct("""
                SELECT so.name, so.customer, so.delivery_date,
                       DATEDIFF(so.delivery_date, CURDATE()) as days_until
                FROM `tabSales Order` so
                WHERE so.docstatus = 1 AND so.status NOT IN ('Completed', 'Cancelled', 'Closed')
                AND so.per_delivered < 100 ORDER BY so.delivery_date LIMIT 10
            """)
            
            # OTIF calculation
            otif = self._query_direct("""
                SELECT COUNT(CASE WHEN dn.posting_date <= so.delivery_date THEN 1 END) * 100.0 / COUNT(*) as rate
                FROM `tabDelivery Note` dn
                JOIN `tabDelivery Note Item` dni ON dni.parent = dn.name
                JOIN `tabSales Order` so ON dni.against_sales_order = so.name
                WHERE dn.docstatus = 1 AND dn.posting_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            """)
            otif_rate = float(otif[0].rate if otif and otif[0].rate else 0)
            otif_status = "🟢" if otif_rate >= 90 else "🟡" if otif_rate >= 75 else "🔴"
            
            msg = f"""## 🐦 Logistics Dashboard
### {today.strftime('%B %Y')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 🚚 Delivery Metrics

| Metric | Value | Status |
|--------|-------|--------|
| Deliveries MTD | {del_count} | - |
| Delivery Value | ${del_value:,.2f} | - |
| OTIF Rate (30d) | {otif_rate:.1f}% | {otif_status} |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### 📦 Upcoming Deliveries

| Order | Customer | Due Date | Days |
|-------|----------|----------|------|
"""
            for p in pending:
                link = f"[{p.name}](https://{self.site_name}/app/sales-order/{p.name})"
                days = f"{p.days_until}" if p.days_until >= 0 else f"⚠️ {abs(p.days_until)} late"
                msg += f"| {link} | {str(p.customer)[:15]} | {p.delivery_date} | {days} |\n"
            
            msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            msg += "💡 **Next:** `@executive alerts` → delivery exceptions"
            
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


# Alias for compatibility
ExecutiveAgent = ExecutiveInsightsAgent
