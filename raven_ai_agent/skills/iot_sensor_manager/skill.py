"""
IoT Sensor Manager Skill
========================
Manages all IoT sensor operations for RPi bots (L01-L30).
Handles temperature, humidity, motion, and general sensor queries.
Logs readings to ERPNext via IoT Sensor Reading DocType.
"""
import frappe
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from raven_ai_agent.skills.framework import SkillBase


SENSOR_TYPES = {
    "temperature": {
        "unit": "C",
        "emoji": "🌡️",
        "thresholds": {"low": 15.0, "high": 35.0, "critical_low": 5.0, "critical_high": 45.0},
        "gpio_pin": 4,
        "sensor_model": "DHT22",
    },
    "humidity": {
        "unit": "%",
        "emoji": "💧",
        "thresholds": {"low": 20.0, "high": 80.0, "critical_low": 10.0, "critical_high": 95.0},
        "gpio_pin": 4,
        "sensor_model": "DHT22",
    },
    "motion": {
        "unit": "boolean",
        "emoji": "🚶",
        "thresholds": {},
        "gpio_pin": 17,
        "sensor_model": "HC-SR501",
    },
    "light": {
        "unit": "lux",
        "emoji": "💡",
        "thresholds": {"low": 50.0, "high": 800.0},
        "gpio_pin": 27,
        "sensor_model": "BH1750",
    },
}


class IoTSensorManagerSkill(SkillBase):
    """Unified skill for managing all IoT sensor operations."""

    name = "iot_sensor_manager"
    description = "Manages IoT sensor readings, alerts, and status for RPi bots L01-L30"
    emoji = "📡"
    version = "1.0.0"
    priority = 70

    triggers = [
        "sensor", "temperature", "humidity", "motion", "light",
        "sensor reading", "sensor status", "iot", "rpi", "bot status",
        "temperatura", "humedad", "movimiento", "sensor data",
        "read sensor", "check sensor", "sensor alert",
    ]

    patterns = [
        r"(?:read|check|get|show|display)\s+(?:the\s+)?(?:temperature|humidity|motion|sensor|light)",
        r"(?:sensor|iot)\s+(?:status|reading|data|alert|report)",
        r"(?:l\d{2})\s+(?:sensor|status|temperature|humidity)",
        r"(?:bot|rpi)\s+(?:l?\d{1,2})\s+(?:sensor|status|data)",
        r"(?:temperatura|humedad|movimiento)\s+(?:de|del|en)\s+(?:l?\d{1,2}|bot)",
    ]

    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        """Route sensor queries to appropriate handler."""
        query_lower = query.lower().strip()

        # Detect bot ID from query
        bot_id = self._extract_bot_id(query_lower)

        # Route to specific handler
        if any(w in query_lower for w in ["status", "estado", "report", "reporte", "all sensor"]):
            return self._handle_status(bot_id, context)
        elif any(w in query_lower for w in ["alert", "alerta", "warning", "critical"]):
            return self._handle_alerts(bot_id, context)
        elif any(w in query_lower for w in ["history", "historial", "trend", "last"]):
            return self._handle_history(bot_id, query_lower, context)
        elif any(w in query_lower for w in ["read", "leer", "check", "get", "medir"]):
            return self._handle_read(bot_id, query_lower, context)
        else:
            return self._handle_status(bot_id, context)

    def _extract_bot_id(self, query: str) -> str:
        """Extract bot ID (e.g., L01) from query string."""
        import re
        match = re.search(r'l(\d{1,2})', query)
        if match:
            num = int(match.group(1))
            return f"L{num:02d}"
        return "L01"  # Default to L01 test bot

    def _handle_read(self, bot_id: str, query: str, context: Dict = None) -> Dict:
        """Handle a sensor reading request."""
        sensor_type = self._detect_sensor_type(query)
        reading = self._get_latest_reading(bot_id, sensor_type)

        if reading:
            cfg = SENSOR_TYPES.get(sensor_type, {})
            emoji = cfg.get("emoji", "📊")
            alert_status = self._check_thresholds(sensor_type, reading.get("value", 0))
            response = (
                f"{emoji} **{sensor_type.title()} Reading - {bot_id}**\n"
                f"Value: {reading['value']} {cfg.get('unit', '')}\n"
                f"Status: {alert_status}\n"
                f"Sensor: {cfg.get('sensor_model', 'N/A')} (GPIO {cfg.get('gpio_pin', 'N/A')})\n"
                f"Timestamp: {reading.get('timestamp', 'N/A')}"
            )
        else:
            response = (
                f"⚠️ No recent {sensor_type} reading found for **{bot_id}**.\n"
                f"The sensor may be offline or not yet configured."
            )

        return {"handled": True, "response": response, "confidence": 0.9}

    def _handle_status(self, bot_id: str, context: Dict = None) -> Dict:
        """Handle sensor status overview for a bot."""
        lines = [f"📡 **IoT Sensor Status - {bot_id}**\n"]

        for sensor_type, cfg in SENSOR_TYPES.items():
            reading = self._get_latest_reading(bot_id, sensor_type)
            emoji = cfg["emoji"]
            if reading:
                alert = self._check_thresholds(sensor_type, reading.get("value", 0))
                lines.append(
                    f"{emoji} {sensor_type.title()}: {reading['value']} {cfg['unit']} [{alert}]"
                )
            else:
                lines.append(f"{emoji} {sensor_type.title()}: -- No data --")

        lines.append(f"\n🕐 Last check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return {"handled": True, "response": "\n".join(lines), "confidence": 0.9}

    def _handle_alerts(self, bot_id: str, context: Dict = None) -> Dict:
        """Handle alert queries."""
        alerts = []
        for sensor_type, cfg in SENSOR_TYPES.items():
            reading = self._get_latest_reading(bot_id, sensor_type)
            if reading:
                status = self._check_thresholds(sensor_type, reading.get("value", 0))
                if status != "✅ Normal":
                    alerts.append(f"{cfg['emoji']} {sensor_type.title()}: {reading['value']} {cfg['unit']} - {status}")

        if alerts:
            response = f"🚨 **Active Alerts - {bot_id}**\n\n" + "\n".join(alerts)
        else:
            response = f"✅ **No active alerts for {bot_id}** - All sensors within normal range."

        return {"handled": True, "response": response, "confidence": 0.9}

    def _handle_history(self, bot_id: str, query: str, context: Dict = None) -> Dict:
        """Handle sensor history queries."""
        sensor_type = self._detect_sensor_type(query)
        readings = self._get_reading_history(bot_id, sensor_type, limit=10)

        if readings:
            cfg = SENSOR_TYPES.get(sensor_type, {})
            lines = [f"📈 **{sensor_type.title()} History - {bot_id}** (Last 10 readings)\n"]
            for r in readings:
                lines.append(f"  {r.get('timestamp', 'N/A')}: {r.get('value', 'N/A')} {cfg.get('unit', '')}")
            response = "\n".join(lines)
        else:
            response = f"📈 No {sensor_type} history available for **{bot_id}**."

        return {"handled": True, "response": response, "confidence": 0.85}

    def _detect_sensor_type(self, query: str) -> str:
        """Detect which sensor type the query refers to."""
        mapping = {
            "temperature": ["temperature", "temp", "temperatura", "calor", "frio"],
            "humidity": ["humidity", "humid", "humedad", "moisture"],
            "motion": ["motion", "movement", "movimiento", "pir", "presence"],
            "light": ["light", "lux", "luminosity", "luz", "brightness"],
        }
        for stype, keywords in mapping.items():
            if any(kw in query for kw in keywords):
                return stype
        return "temperature"  # Default

    def _get_latest_reading(self, bot_id: str, sensor_type: str) -> Optional[Dict]:
        """Get the latest sensor reading from ERPNext."""
        try:
            readings = frappe.get_all(
                "IoT Sensor Reading",
                filters={"bot_id": bot_id, "sensor_type": sensor_type},
                fields=["value", "unit", "timestamp", "status", "gpio_pin"],
                order_by="timestamp desc",
                limit=1,
            )
            if readings:
                return readings[0]
        except Exception as e:
            frappe.logger().error(f"[IoTSensorManager] Error fetching reading: {e}")
        return None

    def _get_reading_history(self, bot_id: str, sensor_type: str, limit: int = 10) -> List[Dict]:
        """Get historical sensor readings."""
        try:
            return frappe.get_all(
                "IoT Sensor Reading",
                filters={"bot_id": bot_id, "sensor_type": sensor_type},
                fields=["value", "unit", "timestamp", "status"],
                order_by="timestamp desc",
                limit=limit,
            )
        except Exception:
            return []

    def _check_thresholds(self, sensor_type: str, value: float) -> str:
        """Check if a sensor value is within acceptable thresholds."""
        cfg = SENSOR_TYPES.get(sensor_type, {})
        thresholds = cfg.get("thresholds", {})

        if not thresholds:
            return "✅ Normal"

        if value <= thresholds.get("critical_low", float("-inf")):
            return "🔴 CRITICAL LOW"
        elif value >= thresholds.get("critical_high", float("inf")):
            return "🔴 CRITICAL HIGH"
        elif value <= thresholds.get("low", float("-inf")):
            return "🟡 Low Warning"
        elif value >= thresholds.get("high", float("inf")):
            return "🟡 High Warning"
        return "✅ Normal"

    @staticmethod
    def log_reading(bot_id: str, sensor_type: str, value: float, gpio_pin: int = None):
        """Log a sensor reading to ERPNext. Called from RPi scripts."""
        cfg = SENSOR_TYPES.get(sensor_type, {})
        try:
            doc = frappe.get_doc({
                "doctype": "IoT Sensor Reading",
                "bot_id": bot_id,
                "sensor_type": sensor_type,
                "value": value,
                "unit": cfg.get("unit", ""),
                "gpio_pin": gpio_pin or cfg.get("gpio_pin"),
                "sensor_model": cfg.get("sensor_model", ""),
                "timestamp": datetime.now(),
                "status": "Active",
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            return doc.name
        except Exception as e:
            frappe.logger().error(f"[IoTSensorManager] Error logging reading: {e}")
            return None
