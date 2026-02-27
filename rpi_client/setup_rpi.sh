#!/bin/bash
# RPi IoT Sensor Setup Script
# Run: bash setup_rpi.sh
echo "=== IoT Sensor Client Setup ==="
sudo apt-get update && sudo apt-get install -y python3-pip python3-dev libgpiod2
pip3 install requests adafruit-circuitpython-dht

# Create env file
cat > /home/pi/.iot_env << 'ENVEOF'
export ERPNEXT_URL="https://v2.sysmayal.cloud"
export ERPNEXT_API_KEY="your_api_key"
export ERPNEXT_API_SECRET="your_api_secret"
export DEVICE_NAME="RPi-L01"
export SENSOR_TYPE="DHT22"
export SENSOR_PIN="4"
export LOCATION="Lab 01"
export READ_INTERVAL="30"
ENVEOF

# Create systemd service
sudo tee /etc/systemd/system/iot-sensor.service << 'SVCEOF'
[Unit]
Description=IoT Sensor Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
EnvironmentFile=/home/pi/.iot_env
ExecStart=/usr/bin/python3 /home/pi/iot_sensor_client.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF

cp iot_sensor_client.py /home/pi/
echo "Edit /home/pi/.iot_env with your API keys"
echo "Then: sudo systemctl enable --now iot-sensor"
