#!/usr/bin/env python3
"""IoT Sensor Client for Raspberry Pi
Reads DHT22 sensor data and sends to ERPNext via Frappe API.

Usage:
    python3 iot_sensor_client.py

Requirements:
    pip3 install requests adafruit-circuitpython-dht
"""
import os
import sys
import time
import json
import socket
import logging
import requests
from datetime import datetime

# Configuration - Edit these for your setup
CONFIG = {
    "erpnext_url": os.getenv("ERPNEXT_URL", "https://v2.sysmayal.cloud"),
    "api_key": os.getenv("ERPNEXT_API_KEY", ""),
    "api_secret": os.getenv("ERPNEXT_API_SECRET", ""),
    "device_name": os.getenv("DEVICE_NAME", socket.gethostname()),
    "sensor_type": os.getenv("SENSOR_TYPE", "DHT22"),
    "sensor_pin": int(os.getenv("SENSOR_PIN", "4")),
    "location": os.getenv("LOCATION", "Lab"),
    "read_interval": int(os.getenv("READ_INTERVAL", "30")),
    "batch_size": int(os.getenv("BATCH_SIZE", "1")),
    "log_level": os.getenv("LOG_LEVEL", "INFO"),
}

logging.basicConfig(
    level=getattr(logging, CONFIG["log_level"]),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/iot_sensor.log")
    ]
)
logger = logging.getLogger(__name__)


def read_dht22(pin):
    """Read temperature and humidity from DHT22 sensor."""
    try:
        import adafruit_dht
        import board
        pin_map = {4: board.D4, 17: board.D17, 27: board.D27, 22: board.D22}
        dht_device = adafruit_dht.DHT22(pin_map.get(pin, board.D4))
        temperature = dht_device.temperature
        humidity = dht_device.humidity
        dht_device.exit()
        if temperature is not None and humidity is not None:
            return {"temperature": round(temperature, 2), "humidity": round(humidity, 2)}
    except ImportError:
        logger.warning("adafruit_dht not installed, using simulated data")
        import random
        return {
            "temperature": round(random.uniform(20, 35), 2),
            "humidity": round(random.uniform(40, 80), 2)
        }
    except Exception as e:
        logger.error(f"Sensor read error: {e}")
    return None


def read_dht11(pin):
    """Read from DHT11 sensor."""
    try:
        import adafruit_dht
        import board
        pin_map = {4: board.D4, 17: board.D17, 27: board.D27, 22: board.D22}
        dht_device = adafruit_dht.DHT11(pin_map.get(pin, board.D4))
        temperature = dht_device.temperature
        humidity = dht_device.humidity
        dht_device.exit()
        if temperature is not None and humidity is not None:
            return {"temperature": round(temperature, 2), "humidity": round(humidity, 2)}
    except ImportError:
        import random
        return {"temperature": round(random.uniform(20, 30), 2), "humidity": round(random.uniform(40, 70), 2)}
    except Exception as e:
        logger.error(f"DHT11 read error: {e}")
    return None


def get_wifi_signal():
    """Get WiFi signal strength."""
    try:
        result = os.popen("iwconfig wlan0 2>/dev/null | grep Signal").read()
        if "Signal level" in result:
            signal = int(result.split("Signal level=")[1].split(" ")[0])
            return signal
    except Exception:
        pass
    return -50


def get_cpu_temp():
    """Get Raspberry Pi CPU temperature."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000.0, 1)
    except Exception:
        return 0


def send_reading(reading_data):
    """Send sensor reading to ERPNext API."""
    url = f"{CONFIG['erpnext_url']}/api/method/raven_ai_agent.raven_ai_agent.api.submit_sensor_reading"
    headers = {
        "Authorization": f"token {CONFIG['api_key']}:{CONFIG['api_secret']}",
        "Content-Type": "application/json"
    }
    try:
        resp = requests.post(url, json=reading_data, headers=headers, timeout=10)
        result = resp.json()
        if resp.status_code == 200 and result.get("message", {}).get("status") == "success":
            logger.info(f"Reading sent: {result['message'].get('name', 'OK')}")
            return True
        else:
            logger.error(f"API error: {result}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Connection error: {e}")
    return False


def main():
    """Main loop: read sensor and send data."""
    logger.info(f"IoT Sensor Client starting - Device: {CONFIG['device_name']}")
    logger.info(f"Sensor: {CONFIG['sensor_type']} on GPIO{CONFIG['sensor_pin']}")
    logger.info(f"Sending to: {CONFIG['erpnext_url']}")
    logger.info(f"Interval: {CONFIG['read_interval']}s")

    sensor_readers = {
        "DHT22": read_dht22,
        "DHT11": read_dht11,
    }
    reader = sensor_readers.get(CONFIG["sensor_type"], read_dht22)
    fail_count = 0

    while True:
        try:
            data = reader(CONFIG["sensor_pin"])
            if data:
                reading = {
                    "sensor_id": f"{CONFIG['device_name']}-{CONFIG['sensor_type']}",
                    "sensor_type": CONFIG["sensor_type"],
                    "device_name": CONFIG["device_name"],
                    "location": CONFIG["location"],
                    "signal_strength": get_wifi_signal(),
                    "reading_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "notes": f"CPU: {get_cpu_temp()}C",
                    **data
                }
                if send_reading(reading):
                    fail_count = 0
                else:
                    fail_count += 1
            else:
                logger.warning("No sensor data")
                fail_count += 1

            # Backoff on repeated failures
            if fail_count > 5:
                wait = min(CONFIG["read_interval"] * fail_count, 300)
                logger.warning(f"Multiple failures, waiting {wait}s")
                time.sleep(wait)
            else:
                time.sleep(CONFIG["read_interval"])

        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(CONFIG["read_interval"])


if __name__ == "__main__":
    main()
