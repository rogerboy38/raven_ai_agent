"""TASKS-337: the dedicated role that lets an author make the agent write. Idempotent; assigns it to nobody
(Hugh assigns it person by person)."""
import frappe

ROLE = "AI Agent Operator"


def execute():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1, "is_custom": 1}).insert(
			ignore_permissions=True
		)
