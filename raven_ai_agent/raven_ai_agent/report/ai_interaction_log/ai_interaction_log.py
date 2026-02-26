# Copyright (c) 2025, Raven AI Agent and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    chart = get_chart_data(data)
    summary = get_report_summary(data)
    return columns, data, None, chart, summary


def get_columns():
    return [
        {
            "label": _("ID"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "AI Memory",
            "width": 120,
        },
        {
            "label": _("User"),
            "fieldname": "user",
            "fieldtype": "Link",
            "options": "User",
            "width": 180,
        },
        {
            "label": _("Memory Type"),
            "fieldname": "memory_type",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("Importance"),
            "fieldname": "importance",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Content"),
            "fieldname": "content",
            "fieldtype": "Text",
            "width": 350,
        },
        {
            "label": _("Source"),
            "fieldname": "source",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("Verified"),
            "fieldname": "verified",
            "fieldtype": "Check",
            "width": 80,
        },
        {
            "label": _("Created On"),
            "fieldname": "creation",
            "fieldtype": "Datetime",
            "width": 160,
        },
        {
            "label": _("Expires On"),
            "fieldname": "expires_on",
            "fieldtype": "Date",
            "width": 110,
        },
    ]


def get_data(filters):
    conditions = build_conditions(filters)
    return frappe.db.sql(
        """
        SELECT
            m.name,
            m.user,
            m.memory_type,
            m.importance,
            m.content,
            m.source,
            m.verified,
            m.creation,
            m.expires_on
        FROM `tabAI Memory` m
        WHERE 1=1 {conditions}
        ORDER BY m.creation DESC
        """.format(conditions=conditions),
        filters,
        as_dict=True,
    )


def build_conditions(filters):
    conditions = ""
    if filters.get("user"):
        conditions += " AND m.user = %(user)s"
    if filters.get("memory_type"):
        conditions += " AND m.memory_type = %(memory_type)s"
    if filters.get("importance"):
        conditions += " AND m.importance = %(importance)s"
    if filters.get("from_date"):
        conditions += " AND m.creation >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND m.creation <= %(to_date)s"
    if filters.get("verified_only"):
        conditions += " AND m.verified = 1"
    return conditions


def get_chart_data(data):
    if not data:
        return None

    type_counts = {}
    for row in data:
        mt = row.get("memory_type") or "Unknown"
        type_counts[mt] = type_counts.get(mt, 0) + 1

    return {
        "data": {
            "labels": list(type_counts.keys()),
            "datasets": [
                {
                    "name": _("Memories by Type"),
                    "values": list(type_counts.values()),
                }
            ],
        },
        "type": "donut",
        "height": 280,
    }


def get_report_summary(data):
    if not data:
        return []

    total = len(data)
    critical = sum(1 for d in data if d.get("importance") == "Critical")
    high = sum(1 for d in data if d.get("importance") == "High")
    verified = sum(1 for d in data if d.get("verified"))

    return [
        {
            "value": total,
            "indicator": "Blue",
            "label": _("Total Memories"),
            "datatype": "Int",
        },
        {
            "value": critical,
            "indicator": "Red",
            "label": _("Critical"),
            "datatype": "Int",
        },
        {
            "value": high,
            "indicator": "Orange",
            "label": _("High Importance"),
            "datatype": "Int",
        },
        {
            "value": verified,
            "indicator": "Green",
            "label": _("Verified"),
            "datatype": "Int",
        },
    ]
