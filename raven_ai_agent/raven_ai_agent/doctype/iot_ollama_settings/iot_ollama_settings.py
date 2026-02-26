import frappe
from frappe.model.document import Document


class IoTOllamaSettings(Document):
    def validate(self):
        if not self.ollama_url:
            self.ollama_url = "http://localhost:11434"
        if not self.default_model:
            self.default_model = "tinyllama"
        if not self.request_timeout:
            self.request_timeout = 120
        # Strip trailing slash from URL
        self.ollama_url = self.ollama_url.rstrip("/")

    @staticmethod
    def get_settings():
        """Get IoT Ollama settings as dict."""
        try:
            settings = frappe.get_single("IoT Ollama Settings")
            return {
                "enabled": bool(settings.enabled),
                "ollama_url": settings.ollama_url or "http://localhost:11434",
                "default_model": settings.default_model or "tinyllama",
                "request_timeout": settings.request_timeout or 120,
                "bot_mention_trigger": settings.bot_mention_trigger or "iot",
                "bot_description": settings.bot_description or "",
            }
        except Exception:
            return {
                "enabled": True,
                "ollama_url": "http://localhost:11434",
                "default_model": "tinyllama",
                "request_timeout": 120,
                "bot_mention_trigger": "iot",
                "bot_description": "IoT Ollama AI Bot",
            }
