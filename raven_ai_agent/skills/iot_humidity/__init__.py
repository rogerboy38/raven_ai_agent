"""
IoT Humidity Skill - Dedicated humidity sensor handler for RPi bots.
Delegates to IoTSensorManagerSkill for unified sensor management.
"""
import frappe
from typing import Dict, Optional
from raven_ai_agent.skills.framework import SkillBase
from raven_ai_agent.skills.iot_sensor_manager.skill import IoTSensorManagerSkill


class IoTHumiditySkill(SkillBase):
    """Specialized skill for humidity sensor operations."""

    name = "iot_humidity"
    description = "Read and monitor humidity from DHT22 sensors on RPi bots"
    emoji = "💧"
    version = "1.0.0"
    priority = 75

    triggers = [
        "humidity", "humid", "humedad", "moisture",
        "dry", "wet", "seco", "mojado",
    ]

    patterns = [
        r"(?:what|how|cual|cuanto).*(?:humidity|humedad|moisture)",
        r"(?:read|check|get|medir).*(?:humidity|humedad|moisture)",
        r"(?:humidity|humedad).*(?:l\d{1,2}|bot)",
    ]

    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        """Handle humidity-specific queries."""
        manager = IoTSensorManagerSkill(agent=self.agent)
        query_lower = query.lower()
        bot_id = manager._extract_bot_id(query_lower)

        if any(w in query_lower for w in ["history", "historial", "trend", "last"]):
            return manager._handle_history(bot_id, "humidity " + query_lower, context)
        elif any(w in query_lower for w in ["alert", "alerta", "warning"]):
            return manager._handle_alerts(bot_id, context)
        else:
            return manager._handle_read(bot_id, "humidity " + query_lower, context)


SKILL_CLASS = IoTHumiditySkill
