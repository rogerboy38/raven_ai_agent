"""
IoT Temperature Skill - Dedicated temperature sensor handler for RPi bots.
Delegates to IoTSensorManagerSkill for unified sensor management.
"""
import frappe
from typing import Dict, Optional
from raven_ai_agent.skills.framework import SkillBase
from raven_ai_agent.skills.iot_sensor_manager.skill import IoTSensorManagerSkill, SENSOR_TYPES


class IoTTemperatureSkill(SkillBase):
    """Specialized skill for temperature sensor operations."""

    name = "iot_temperature"
    description = "Read and monitor temperature from DHT22 sensors on RPi bots"
    emoji = "🌡️"
    version = "1.0.0"
    priority = 75  # Higher priority for specific temperature queries

    triggers = [
        "temperature", "temp", "temperatura", "calor", "frio",
        "hot", "cold", "degrees", "celsius", "grados",
    ]

    patterns = [
        r"(?:what|how|cual|cuanto).*(?:temperature|temp|temperatura)",
        r"(?:read|check|get|medir).*(?:temperature|temp|temperatura)",
        r"(?:temperature|temp|temperatura).*(?:l\d{1,2}|bot)",
    ]

    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        """Handle temperature-specific queries."""
        manager = IoTSensorManagerSkill(agent=self.agent)
        query_lower = query.lower()
        bot_id = manager._extract_bot_id(query_lower)

        if any(w in query_lower for w in ["history", "historial", "trend", "last"]):
            return manager._handle_history(bot_id, "temperature " + query_lower, context)
        elif any(w in query_lower for w in ["alert", "alerta", "warning"]):
            result = manager._handle_alerts(bot_id, context)
            return result
        else:
            return manager._handle_read(bot_id, "temperature " + query_lower, context)


SKILL_CLASS = IoTTemperatureSkill
