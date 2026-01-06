import frappe
from frappe.model.document import Document

class AIMemory(Document):
    def before_insert(self):
        # Auto-set user if not specified
        if not self.user:
            self.user = frappe.session.user
    
    def validate(self):
        # Check for duplicate critical facts
        if self.importance == "Critical":
            existing = frappe.db.exists("AI Memory", {
                "user": self.user,
                "content": self.content,
                "importance": "Critical",
                "name": ["!=", self.name or ""]
            })
            if existing:
                frappe.throw("This critical fact already exists")
