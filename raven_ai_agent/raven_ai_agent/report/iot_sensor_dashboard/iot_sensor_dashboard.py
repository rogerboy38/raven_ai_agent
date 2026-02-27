import frappe
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    chart = get_chart(data)
    report_summary = get_summary(filters)
    return columns, data, None, chart, report_summary

def get_columns():
    return [
        {"fieldname": "device_name", "label": _("Device"), "fieldtype": "Data", "width": 120},
        {"fieldname": "sensor_type", "label": _("Sensor"), "fieldtype": "Data", "width": 100},
        {"fieldname": "temperature", "label": _("Temp (C)"), "fieldtype": "Float", "width": 100},
        {"fieldname": "humidity", "label": _("Humidity %"), "fieldtype": "Float", "width": 100},
        {"fieldname": "location", "label": _("Location"), "fieldtype": "Data", "width": 120},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 80},
        {"fieldname": "signal_strength", "label": _("Signal dBm"), "fieldtype": "Int", "width": 90},
        {"fieldname": "reading_timestamp", "label": _("Timestamp"), "fieldtype": "Datetime", "width": 160},
        {"fieldname": "name", "label": _("ID"), "fieldtype": "Link", "options": "IoT Sensor Reading", "width": 130},
    ]

def get_data(filters):
    conditions = ""
    if filters:
        if filters.get("device_name"):
            conditions += f" AND device_name = '{filters['device_name']}'"
        if filters.get("sensor_type"):
            conditions += f" AND sensor_type = '{filters['sensor_type']}'"
        if filters.get("from_date"):
            conditions += f" AND reading_timestamp >= '{filters['from_date']}'"
        if filters.get("to_date"):
            conditions += f" AND reading_timestamp <= '{filters['to_date']}'"
    return frappe.db.sql(f"""
        SELECT device_name, sensor_type, temperature, humidity,
               location, status, signal_strength, reading_timestamp, name
        FROM `tabIoT Sensor Reading`
        WHERE 1=1 {conditions}
        ORDER BY reading_timestamp DESC
        LIMIT 200
    """, as_dict=True)

def get_chart(data):
    if not data:
        return None
    labels = [d.get("reading_timestamp", "")[:16] for d in reversed(data[:50])]
    temps = [d.get("temperature", 0) for d in reversed(data[:50])]
    humids = [d.get("humidity", 0) for d in reversed(data[:50])]
    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": _("Temperature"), "values": temps},
                {"name": _("Humidity"), "values": humids}
            ]
        },
        "type": "line",
        "colors": ["#ff5858", "#5b8ff9"]
    }

def get_summary(filters):
    conditions = ""
    if filters:
        if filters.get("device_name"):
            conditions += f" AND device_name = '{filters['device_name']}'"
    result = frappe.db.sql(f"""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT device_name) as devices,
               ROUND(AVG(temperature),1) as avg_temp,
               ROUND(AVG(humidity),1) as avg_humidity
        FROM `tabIoT Sensor Reading`
        WHERE 1=1 {conditions}
    """, as_dict=True)[0]
    return [
        {"value": result.total, "label": _("Total Readings"), "datatype": "Int"},
        {"value": result.devices, "label": _("Active Devices"), "datatype": "Int"},
        {"value": result.avg_temp, "label": _("Avg Temp (C)"), "datatype": "Float", "indicator": "orange" if (result.avg_temp or 0) > 35 else "green"},
        {"value": result.avg_humidity, "label": _("Avg Humidity %"), "datatype": "Float", "indicator": "blue"},
    ]
