import frappe
from frappe import _
import json
from datetime import datetime


@frappe.whitelist(allow_guest=False)
def submit_sensor_reading(**kwargs):
    """API endpoint for RPi to submit sensor readings.
    
    POST /api/method/raven_ai_agent.raven_ai_agent.api.submit_sensor_reading
    
    Args:
        sensor_id: Unique sensor identifier (e.g., 'RPi-L01-DHT22')
        sensor_type: Type of sensor (Temperature, Humidity, Pressure, Light, Multi)
        device_name: Device name (e.g., 'RPi-L01')
        temperature: Temperature reading in Celsius
        humidity: Humidity percentage
        pressure: Pressure in hPa (optional)
        light_level: Light level in lux (optional)
        location: Location description (optional)
        latitude: GPS latitude (optional)
        longitude: GPS longitude (optional)
        battery_level: Battery percentage (optional)
        signal_strength: WiFi signal in dBm (optional)
        notes: Additional notes (optional)
        reading_timestamp: ISO timestamp of reading (optional, defaults to now)
    """
    try:
        doc = frappe.get_doc({
            "doctype": "IoT Sensor Reading",
            "sensor_id": kwargs.get("sensor_id"),
            "sensor_type": kwargs.get("sensor_type", "DHT22"),
            "device_name": kwargs.get("device_name"),
            "temperature": float(kwargs.get("temperature", 0)),
            "humidity": float(kwargs.get("humidity", 0)),
            "pressure": float(kwargs.get("pressure", 0)),
            "light_level": float(kwargs.get("light_level", 0)),
            "location": kwargs.get("location", ""),
            "latitude": float(kwargs.get("latitude", 0)),
            "longitude": float(kwargs.get("longitude", 0)),
            "status": kwargs.get("status", "Active"),
            "battery_level": float(kwargs.get("battery_level", 0)),
            "signal_strength": int(kwargs.get("signal_strength", 0)),
            "notes": kwargs.get("notes", ""),
            "reading_timestamp": kwargs.get("reading_timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        # Check thresholds and send Raven alert if needed
        _check_thresholds(doc)

        return {
            "status": "success",
            "name": doc.name,
            "message": f"Sensor reading {doc.name} created successfully"
        }
    except Exception as e:
        frappe.log_error(f"IoT Sensor Reading Error: {str(e)}", "IoT API Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def submit_batch_readings(**kwargs):
    """Submit multiple sensor readings at once.
    
    POST /api/method/raven_ai_agent.raven_ai_agent.api.submit_batch_readings
    
    Args:
        readings: JSON array of reading objects
    """
    readings = kwargs.get("readings", [])
    if isinstance(readings, str):
        readings = json.loads(readings)

    results = []
    for reading in readings:
        result = submit_sensor_reading(**reading)
        results.append(result)

    return {
        "status": "success",
        "count": len(results),
        "results": results
    }


@frappe.whitelist(allow_guest=False)
def get_latest_readings(device_name=None, sensor_type=None, limit=10):
    """Get latest sensor readings with optional filters.
    
    GET /api/method/raven_ai_agent.raven_ai_agent.api.get_latest_readings
    """
    filters = {}
    if device_name:
        filters["device_name"] = device_name
    if sensor_type:
        filters["sensor_type"] = sensor_type

    readings = frappe.get_all(
        "IoT Sensor Reading",
        filters=filters,
        fields=["name", "sensor_id", "sensor_type", "device_name",
                "temperature", "humidity", "pressure", "light_level",
                "location", "status", "reading_timestamp",
                "battery_level", "signal_strength"],
        order_by="reading_timestamp desc",
        limit_page_length=int(limit)
    )
    return {"status": "success", "count": len(readings), "readings": readings}


@frappe.whitelist(allow_guest=False)
def get_device_status(device_name):
    """Get the current status of a specific device based on its latest reading."""
    latest = frappe.get_all(
        "IoT Sensor Reading",
        filters={"device_name": device_name},
        fields=["*"],
        order_by="reading_timestamp desc",
        limit_page_length=1
    )
    if not latest:
        return {"status": "error", "message": f"No readings found for {device_name}"}

    reading = latest[0]
    # Check if device is stale (no reading in last 5 minutes)
    from frappe.utils import now_datetime, get_datetime
    last_reading_time = get_datetime(reading.get("reading_timestamp") or reading.get("creation"))
    diff = (now_datetime() - last_reading_time).total_seconds()
    is_online = diff < 300  # 5 minutes

    return {
        "status": "success",
        "device_name": device_name,
        "is_online": is_online,
        "last_seen_seconds_ago": int(diff),
        "latest_reading": reading
    }


def _check_thresholds(doc):
    """Check sensor thresholds and send Raven message if exceeded."""
    alerts = []
    
    if doc.temperature and float(doc.temperature) > 40:
        alerts.append(f"HIGH TEMP: {doc.temperature}C on {doc.device_name}")
    if doc.temperature and float(doc.temperature) < 0:
        alerts.append(f"LOW TEMP: {doc.temperature}C on {doc.device_name}")
    if doc.humidity and float(doc.humidity) > 85:
        alerts.append(f"HIGH HUMIDITY: {doc.humidity}% on {doc.device_name}")
    if doc.battery_level and float(doc.battery_level) < 20:
        alerts.append(f"LOW BATTERY: {doc.battery_level}% on {doc.device_name}")

    if alerts:
        try:
            _send_raven_alert(doc.device_name, alerts)
        except Exception as e:
            frappe.log_error(f"Raven alert error: {str(e)}", "IoT Raven Alert Error")


def _send_raven_alert(device_name, alerts):
    """Send alert message to Raven channel."""
    # Find the IoT alerts channel in Raven
    channel = frappe.db.get_value("Raven Channel",
        {"channel_name": ["like", "%iot%"]}, "name")
    
    if not channel:
        # Try to find any general channel
        channel = frappe.db.get_value("Raven Channel",
            {"channel_name": ["like", "%general%"]}, "name")
    
    if channel:
        alert_text = f"IoT ALERT from {device_name}:\n" + "\n".join(f"  {a}" for a in alerts)
        raven_msg = frappe.get_doc({
            "doctype": "Raven Message",
            "channel_id": channel,
            "text": alert_text,
            "message_type": "Text"
        })
        raven_msg.insert(ignore_permissions=True)
        frappe.db.commit()
