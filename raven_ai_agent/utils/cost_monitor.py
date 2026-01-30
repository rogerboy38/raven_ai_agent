"""
LLM Cost Monitor & Budget Management
Tracks usage, costs, and provides warnings when spending increases

Features:
- Real-time cost tracking per provider/model
- Budget limits with warnings
- Usage analytics
- Cost optimization suggestions
"""

import frappe
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class UsageRecord:
    """Single usage record"""
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    timestamp: datetime
    user: str
    query_type: str = "chat"


class CostMonitor:
    """
    LLM Cost Monitor
    
    Tracks all API calls, calculates costs, and provides warnings
    when spending exceeds thresholds.
    """
    
    # Pricing per 1M tokens (USD)
    PRICING = {
        # OpenAI
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        
        # DeepSeek
        "deepseek-chat": {"input": 0.14, "output": 0.28},
        "deepseek-reasoner": {"input": 0.55, "output": 2.19},
        
        # Claude
        "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
        "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
        
        # MiniMax
        "abab6.5s-chat": {"input": 1.00, "output": 4.00},
        "abab6.5g-chat": {"input": 0.50, "output": 2.00},
        "abab5.5-chat": {"input": 0.20, "output": 0.80},
    }
    
    def __init__(self):
        self.settings = self._load_settings()
    
    def _load_settings(self) -> Dict:
        """Load cost monitoring settings"""
        try:
            settings = frappe.get_single("AI Agent Settings")
            return {
                "daily_budget": getattr(settings, "daily_budget", 10.0),
                "monthly_budget": getattr(settings, "monthly_budget", 100.0),
                "warning_threshold": getattr(settings, "budget_warning_threshold", 0.8),
                "critical_threshold": getattr(settings, "budget_critical_threshold", 0.95),
                "enable_cost_tracking": getattr(settings, "enable_cost_tracking", True),
                "block_on_budget_exceeded": getattr(settings, "block_on_budget_exceeded", False),
            }
        except Exception:
            return {
                "daily_budget": 10.0,
                "monthly_budget": 100.0,
                "warning_threshold": 0.8,
                "critical_threshold": 0.95,
                "enable_cost_tracking": True,
                "block_on_budget_exceeded": False,
            }
    
    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int
    ) -> float:
        """Calculate cost for a request"""
        pricing = self.PRICING.get(model, {"input": 1.0, "output": 2.0})
        
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        
        return round(input_cost + output_cost, 6)
    
    def record_usage(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        user: str = None
    ) -> Tuple[float, Optional[Dict]]:
        """
        Record API usage and check budget
        
        Returns:
            (cost, alert) - cost in USD and optional alert dict
        """
        if not self.settings.get("enable_cost_tracking"):
            return 0.0, None
        
        cost = self.calculate_cost(model, input_tokens, output_tokens)
        user = user or frappe.session.user
        
        # Store in database
        try:
            doc = frappe.get_doc({
                "doctype": "AI Usage Log",
                "user": user,
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
                "timestamp": datetime.now()
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            # Log might not exist, just track in memory
            frappe.logger().warning(f"[CostMonitor] Could not log usage: {e}")
        
        # Check budgets and generate alerts
        alert = self._check_budgets(cost)
        
        return cost, alert
    
    def _check_budgets(self, latest_cost: float) -> Optional[Dict]:
        """Check if any budget thresholds are exceeded"""
        daily_usage = self.get_usage_period("day")
        monthly_usage = self.get_usage_period("month")
        
        daily_budget = self.settings["daily_budget"]
        monthly_budget = self.settings["monthly_budget"]
        warning_pct = self.settings["warning_threshold"]
        critical_pct = self.settings["critical_threshold"]
        
        alerts = []
        
        # Check daily budget
        daily_pct = daily_usage / daily_budget if daily_budget > 0 else 0
        if daily_pct >= critical_pct:
            alerts.append({
                "level": AlertLevel.CRITICAL,
                "type": "daily_budget",
                "message": f"🚨 CRITICAL: Daily budget {daily_pct*100:.0f}% used (${daily_usage:.2f}/${daily_budget:.2f})",
                "usage_pct": daily_pct
            })
        elif daily_pct >= warning_pct:
            alerts.append({
                "level": AlertLevel.WARNING,
                "type": "daily_budget",
                "message": f"⚠️ WARNING: Daily budget {daily_pct*100:.0f}% used (${daily_usage:.2f}/${daily_budget:.2f})",
                "usage_pct": daily_pct
            })
        
        # Check monthly budget
        monthly_pct = monthly_usage / monthly_budget if monthly_budget > 0 else 0
        if monthly_pct >= critical_pct:
            alerts.append({
                "level": AlertLevel.CRITICAL,
                "type": "monthly_budget",
                "message": f"🚨 CRITICAL: Monthly budget {monthly_pct*100:.0f}% used (${monthly_usage:.2f}/${monthly_budget:.2f})",
                "usage_pct": monthly_pct
            })
        elif monthly_pct >= warning_pct:
            alerts.append({
                "level": AlertLevel.WARNING,
                "type": "monthly_budget",
                "message": f"⚠️ WARNING: Monthly budget {monthly_pct*100:.0f}% used (${monthly_usage:.2f}/${monthly_budget:.2f})",
                "usage_pct": monthly_pct
            })
        
        # Check for sudden spike (>3x normal hourly rate)
        hourly_usage = self.get_usage_period("hour")
        avg_hourly = self._get_average_hourly_usage()
        if avg_hourly > 0 and hourly_usage > avg_hourly * 3:
            alerts.append({
                "level": AlertLevel.WARNING,
                "type": "usage_spike",
                "message": f"📈 SPIKE: Current hour ${hourly_usage:.2f} vs avg ${avg_hourly:.2f}/hr",
                "current": hourly_usage,
                "average": avg_hourly
            })
        
        return alerts[0] if alerts else None
    
    def get_usage_period(self, period: str) -> float:
        """Get total usage for a period (hour, day, week, month)"""
        try:
            if period == "hour":
                start = datetime.now() - timedelta(hours=1)
            elif period == "day":
                start = datetime.now().replace(hour=0, minute=0, second=0)
            elif period == "week":
                start = datetime.now() - timedelta(days=7)
            elif period == "month":
                start = datetime.now().replace(day=1, hour=0, minute=0, second=0)
            else:
                start = datetime.now() - timedelta(days=1)
            
            result = frappe.db.sql("""
                SELECT COALESCE(SUM(cost_usd), 0) as total
                FROM `tabAI Usage Log`
                WHERE timestamp >= %s
            """, (start,), as_dict=True)
            
            return float(result[0]["total"]) if result else 0.0
        except Exception:
            return 0.0
    
    def _get_average_hourly_usage(self) -> float:
        """Get average hourly usage over past 7 days"""
        try:
            result = frappe.db.sql("""
                SELECT COALESCE(SUM(cost_usd), 0) / 168 as avg_hourly
                FROM `tabAI Usage Log`
                WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            """, as_dict=True)
            return float(result[0]["avg_hourly"]) if result else 0.0
        except Exception:
            return 0.0
    
    def get_usage_report(self, days: int = 30) -> Dict:
        """Generate usage report"""
        try:
            # By provider
            by_provider = frappe.db.sql("""
                SELECT provider, 
                       SUM(input_tokens) as total_input,
                       SUM(output_tokens) as total_output,
                       SUM(cost_usd) as total_cost,
                       COUNT(*) as requests
                FROM `tabAI Usage Log`
                WHERE timestamp >= DATE_SUB(NOW(), INTERVAL %s DAY)
                GROUP BY provider
                ORDER BY total_cost DESC
            """, (days,), as_dict=True)
            
            # By model
            by_model = frappe.db.sql("""
                SELECT model,
                       SUM(cost_usd) as total_cost,
                       COUNT(*) as requests
                FROM `tabAI Usage Log`
                WHERE timestamp >= DATE_SUB(NOW(), INTERVAL %s DAY)
                GROUP BY model
                ORDER BY total_cost DESC
            """, (days,), as_dict=True)
            
            # By user
            by_user = frappe.db.sql("""
                SELECT user,
                       SUM(cost_usd) as total_cost,
                       COUNT(*) as requests
                FROM `tabAI Usage Log`
                WHERE timestamp >= DATE_SUB(NOW(), INTERVAL %s DAY)
                GROUP BY user
                ORDER BY total_cost DESC
                LIMIT 10
            """, (days,), as_dict=True)
            
            # Daily trend
            daily_trend = frappe.db.sql("""
                SELECT DATE(timestamp) as date,
                       SUM(cost_usd) as cost
                FROM `tabAI Usage Log`
                WHERE timestamp >= DATE_SUB(NOW(), INTERVAL %s DAY)
                GROUP BY DATE(timestamp)
                ORDER BY date
            """, (days,), as_dict=True)
            
            return {
                "period_days": days,
                "total_cost": sum(p["total_cost"] for p in by_provider),
                "total_requests": sum(p["requests"] for p in by_provider),
                "by_provider": by_provider,
                "by_model": by_model,
                "by_user": by_user,
                "daily_trend": daily_trend,
                "recommendations": self._get_cost_recommendations(by_model)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _get_cost_recommendations(self, by_model: List[Dict]) -> List[str]:
        """Generate cost optimization recommendations"""
        recommendations = []
        
        for item in by_model:
            model = item["model"]
            cost = item["total_cost"]
            
            # Suggest cheaper alternatives
            if model == "gpt-4o" and cost > 5:
                recommendations.append(
                    f"💡 Consider using gpt-4o-mini for routine queries. "
                    f"You spent ${cost:.2f} on gpt-4o. Mini is 16x cheaper."
                )
            
            if model == "claude-3-opus-20240229" and cost > 10:
                recommendations.append(
                    f"💡 Consider claude-3-5-sonnet for most tasks. "
                    f"You spent ${cost:.2f} on Opus. Sonnet is 5x cheaper with similar quality."
                )
            
            if model in ["gpt-4o", "claude-3-5-sonnet-20241022"] and cost > 20:
                recommendations.append(
                    f"💡 DeepSeek offers similar quality at 10-20x lower cost. "
                    f"Consider deepseek-chat for routine ERPNext queries."
                )
        
        return recommendations
    
    def should_block_request(self) -> Tuple[bool, Optional[str]]:
        """Check if request should be blocked due to budget"""
        if not self.settings.get("block_on_budget_exceeded"):
            return False, None
        
        daily_usage = self.get_usage_period("day")
        monthly_usage = self.get_usage_period("month")
        
        if daily_usage >= self.settings["daily_budget"]:
            return True, f"Daily budget exceeded (${daily_usage:.2f}/${self.settings['daily_budget']:.2f})"
        
        if monthly_usage >= self.settings["monthly_budget"]:
            return True, f"Monthly budget exceeded (${monthly_usage:.2f}/${self.settings['monthly_budget']:.2f})"
        
        return False, None


# Singleton instance
_cost_monitor = None

def get_cost_monitor() -> CostMonitor:
    """Get or create cost monitor instance"""
    global _cost_monitor
    if _cost_monitor is None:
        _cost_monitor = CostMonitor()
    return _cost_monitor


# API Endpoints

@frappe.whitelist()
def get_usage_report(days: int = 30) -> Dict:
    """API: Get usage report"""
    monitor = get_cost_monitor()
    return monitor.get_usage_report(days)


@frappe.whitelist()
def get_current_usage() -> Dict:
    """API: Get current usage status"""
    monitor = get_cost_monitor()
    return {
        "hourly": monitor.get_usage_period("hour"),
        "daily": monitor.get_usage_period("day"),
        "weekly": monitor.get_usage_period("week"),
        "monthly": monitor.get_usage_period("month"),
        "daily_budget": monitor.settings["daily_budget"],
        "monthly_budget": monitor.settings["monthly_budget"],
        "daily_pct": monitor.get_usage_period("day") / monitor.settings["daily_budget"] * 100,
        "monthly_pct": monitor.get_usage_period("month") / monitor.settings["monthly_budget"] * 100,
    }


@frappe.whitelist()
def get_model_pricing() -> Dict:
    """API: Get pricing for all models"""
    return CostMonitor.PRICING
