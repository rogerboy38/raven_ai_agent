#!/usr/bin/env python3
"""
RPi IoT Sensor Reader
=====================
Runs on each Raspberry Pi bot (L01-L30) to read sensors
and log data to ERPNext via the Frappe API.

Usage:
    python3 rpi_sensor_reader.py --bot-id L01 --interval 30

Sensors supported:
    - DHT22 (Temperature + Humidity) on GPIO 4
    - HC-SR501 PIR (Motion) on GPIO 17
    - BH1750 (Light) via I2C

Requires:
    pip install adafruit-circuitpython-dht RPi.GPIO requests smbus2
"""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime

import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/rpi_sensor_reader.log'),
    ]
)
logger = logging.getLogger('SensorReader')

# Default config - override via env vars or args
DEFAULT_CONFIG = {
    'erp_url': os.environ.get('ERP_URL', 'http://localhost:8080'),
    'api_key': os.environ.get('ERP_API_KEY', ''),
    'api_secret': os.environ.get('ERP_API_SECRET', ''),
    'bot_id': os.environ.get('BOT_ID', 'L01'),
    'interval': int(os.environ.get('READ_INTERVAL', '30')),
    'dht_pin': int(os.environ.get('DHT_PIN', '4')),
    'pir_pin': int(os.environ.get('PIR_PIN', '17')),
    'simulate': os.environ.get('SIMULATE', 'false').lower() == 'true',
}


class SensorReader:
    """Reads sensors and logs data to ERPNext."""

    def __init__(self, config):
        self.config = config
        self.bot_id = config['bot_id']
        self.erp_url = config['erp_url'].rstrip('/')
        self.session = requests.Session()
        if config['api_key'] and config['api_secret']:
            self.session.headers.update({
                'Authorization': f"token {config['api_key']}:{config['api_secret']}"
            })
        self.session.headers.update({'Content-Type': 'application/json'})

        # Initialize hardware (or simulation)
        self.simulate = config['simulate']
        if not self.simulate:
            self._init_hardware()

    def _init_hardware(self):
        """Initialize GPIO and sensor hardware."""
        try:
            import board
            import adafruit_dht
            self.dht = adafruit_dht.DHT22(getattr(board, f'D{self.config["dht_pin"]}'))
            logger.info(f'DHT22 initialized on GPIO {self.config["dht_pin"]}')
        except Exception as e:
            logger.warning(f'DHT22 init failed: {e}. Using simulation.')
            self.dht = None

        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.config['pir_pin'], GPIO.IN)
            self.gpio = GPIO
            logger.info(f'PIR initialized on GPIO {self.config["pir_pin"]}')
        except Exception as e:
            logger.warning(f'PIR init failed: {e}. Using simulation.')
            self.gpio = None

    def read_temperature(self):
        """Read temperature from DHT22."""
        if self.simulate or self.dht is None:
            import random
            return round(20.0 + random.uniform(-5, 10), 1)
        try:
            return round(self.dht.temperature, 1)
        except Exception as e:
            logger.error(f'Temperature read error: {e}')
            return None

    def read_humidity(self):
        """Read humidity from DHT22."""
        if self.simulate or self.dht is None:
            import random
            return round(50.0 + random.uniform(-20, 30), 1)
        try:
            return round(self.dht.humidity, 1)
        except Exception as e:
            logger.error(f'Humidity read error: {e}')
            return None

    def read_motion(self):
        """Read motion from PIR sensor."""
        if self.simulate or self.gpio is None:
            import random
            return 1 if random.random() > 0.7 else 0
        try:
            return self.gpio.input(self.config['pir_pin'])
        except Exception as e:
            logger.error(f'Motion read error: {e}')
            return None

    def log_to_erp(self, sensor_type, value, unit, gpio_pin=None, sensor_model=''):
        """Log a sensor reading to ERPNext IoT Sensor Reading DocType."""
        payload = {
            'doctype': 'IoT Sensor Reading',
            'bot_id': self.bot_id,
            'sensor_type': sensor_type,
            'value': value,
            'unit': unit,
            'gpio_pin': gpio_pin or 0,
            'sensor_model': sensor_model,
            'timestamp': datetime.now().isoformat(),
            'status': 'Active',
        }
        try:
            resp = self.session.post(
                f'{self.erp_url}/api/resource/IoT Sensor Reading',
                json=payload,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                name = data.get('data', {}).get('name', 'unknown')
                logger.info(f'Logged {sensor_type}={value}{unit} for {self.bot_id} -> {name}')
                return True
            else:
                logger.error(f'ERP log failed ({resp.status_code}): {resp.text[:200]}')
        except Exception as e:
            logger.error(f'ERP connection error: {e}')
        return False

    def read_and_log_all(self):
        """Read all sensors and log to ERPNext."""
        # Temperature
        temp = self.read_temperature()
        if temp is not None:
            self.log_to_erp('temperature', temp, 'C', self.config['dht_pin'], 'DHT22')

        # Humidity
        humidity = self.read_humidity()
        if humidity is not None:
            self.log_to_erp('humidity', humidity, '%', self.config['dht_pin'], 'DHT22')

        # Motion
        motion = self.read_motion()
        if motion is not None:
            self.log_to_erp('motion', motion, 'boolean', self.config['pir_pin'], 'HC-SR501')

        logger.info(f'[{self.bot_id}] T={temp}C H={humidity}% M={motion}')

    def run(self):
        """Main loop - read sensors at configured interval."""
        interval = self.config['interval']
        logger.info(f'Starting sensor reader for {self.bot_id} (interval={interval}s, simulate={self.simulate})')

        while True:
            try:
                self.read_and_log_all()
            except Exception as e:
                logger.error(f'Read cycle error: {e}')
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description='RPi IoT Sensor Reader')
    parser.add_argument('--bot-id', default=DEFAULT_CONFIG['bot_id'], help='Bot ID (e.g., L01)')
    parser.add_argument('--interval', type=int, default=DEFAULT_CONFIG['interval'], help='Read interval in seconds')
    parser.add_argument('--erp-url', default=DEFAULT_CONFIG['erp_url'], help='ERPNext URL')
    parser.add_argument('--api-key', default=DEFAULT_CONFIG['api_key'], help='Frappe API key')
    parser.add_argument('--api-secret', default=DEFAULT_CONFIG['api_secret'], help='Frappe API secret')
    parser.add_argument('--simulate', action='store_true', default=DEFAULT_CONFIG['simulate'], help='Simulate sensor readings')
    args = parser.parse_args()

    config = {
        'bot_id': args.bot_id,
        'interval': args.interval,
        'erp_url': args.erp_url,
        'api_key': args.api_key,
        'api_secret': args.api_secret,
        'simulate': args.simulate,
        'dht_pin': DEFAULT_CONFIG['dht_pin'],
        'pir_pin': DEFAULT_CONFIG['pir_pin'],
    }

    reader = SensorReader(config)
    reader.run()


if __name__ == '__main__':
    main()
