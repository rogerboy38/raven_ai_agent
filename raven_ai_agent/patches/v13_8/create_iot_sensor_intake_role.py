"""TASKS-344 ruling 81(4): the narrow role of the IoT sensor intake (the RPi's API user). Idempotent; assigns it to
nobody (Hugh assigns it to that one user). It replaces the System Manager requirement of ruling 76 for
`submit_sensor_reading` only."""
import frappe

ROLE = "IoT Sensor Intake"


def execute():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 0, "is_custom": 1}).insert(
			ignore_permissions=True
		)
