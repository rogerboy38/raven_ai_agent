"""
IoT Motion Skill - Dedicated motion/PIR sensor handler for RPi bots.
Delegates to IoTSensorManagerSkill for unified sensor management.
"""
import frappe
from typing import Dict, Optional
from raven_ai_agent.skills.framework import SkillBase
from raven_ai_agent.skills.iot_sensor_manager.skill import IoTSensorManagerSkill


class IoTMotionSkill(SkillBase):
    """Specialized skill for motion/PIR sensor operations."""

    name = "iot_motion"
    description = "Detect and monitor motion from HC-SR501 PIR sensors on RPi bots"
    emoji = "🚶"
    version = "1.0.0"
    priority = 75

    triggers = [
        "motion", "movement", "movimiento", "pir",
        "presence", "presencia", "detect", "intruder",
    ]

    patterns = [
        r"(?:any|is there|hay).*(?:motion|movement|movimiento)",
        r"(?:detect|check|monitor).*(?:motion|movement|presence)",
        r"(?:motion|movement|pir).*(?:l\d{1,2}|bot)",
    ]

    def handle(self, query: str, context: Dict = None) -> Optional[Dict]:
        """Handle motion-specific queries."""
        manager = IoTSensorManagerSkill(agent=self.agent)
        query_lower = query.lower()
        bot_id = manager._extract_bot_id(query_lower)

        if any(w in query_lower for w in ["history", "historial", "log", "last"]):
            return manager._handle_history(bot_id, "motion " + query_lower, context)
        else:
            return manager._handle_read(bot_id, "motion " + query_lower, context)


SKILL_CLASS = IoTMotionSkill
