# RPi Client - Scale Weight Capture System

Raspberry Pi client for AMB Batch manufacturing workflow weight capture.

**PH13.2.0 Integration**: This version integrates with `amb_w_spc` Sensor Skill configuration for automatic scale setup.

## Features

- **Terminal Mode**: Type barrel serial and weight directly
- **Mobile Web UI**: Flask app accessible from phone browsers
- **Multiple Backends**: Keyboard, serial scale, camera barcode (stubs)
- **Offline Buffer**: SQLite-based buffering for failed submissions
- **Raven Notifications**: Success alerts to iot-lab channel
- **PH13.2.0 Sensor Skill**: Auto-configures scale from ERPNext settings

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   Mode A/B/C/D  │     │   Flask Web UI  │
│  (Input Modes)  │     │  (Mobile App)   │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │  weight_capture_     │
         │  client.py / web_app │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │  Sensor Skill Client │
         │  sensor_skill_client │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │     ERPNext API       │
         │  amb_w_spc.api        │
         └───────────────────────┘
```

## Installation

### Prerequisites

- Raspberry Pi with Python 3.11+
- ngrok account and authtoken

### Setup

```bash
# Clone to Raspberry Pi
cd ~/raven-bot
git clone <repo_url> .

# Create virtual environment
python3 -m venv raven-env
source raven-env/bin/activate

# Install dependencies
pip install -r rpi_client/requirements.txt

# Configure environment
cat > .env << 'EOF'
export ERPNEXT_URL="http://sysmayal.ngrok.io"
export ERPNEXT_API_KEY="your_api_key"
export ERPNEXT_API_SECRET="your_api_secret"
export DEVICE_ID="SCALE-L01"
export RAVEN_CHANNEL="iot-lab"
export SCALE_BACKEND="keyboard"
export BARCODE_BACKEND="keyboard"
EOF

# Configure ngrok
mkdir -p ~/.config/ngrok
cat > ~/.config/ngrok/ngrok.yml << 'EOF'
version: "3"
agent:
    authtoken: <your_token>
tunnels:
  bot-iot-web:
    proto: http
    addr: 5000
    domain: bot1.sysmayal.ngrok.io
EOF
```

## Usage

### Terminal Mode

```bash
source .env
python3 rpi_client/weight_capture_client.py
```

Menu:
1. Scan/Enter barrel serial
2. Read/Enter weight
3. Submit to ERPNext
4. View pending submissions
5. Retry pending
6. View history
7. Settings
0. Exit

### Mobile Web UI

```bash
# Start all services
./rpi_client/start_all.sh

# Or start individually
source raven-env/bin/activate
python3 rpi_client/web_app.py

# In another terminal
ngrok start bot-iot-web
```

Access: https://bot1.sysmayal.ngrok.io

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| ERPNEXT_URL | http://sysmayal.ngrok.io | ERPNext server URL |
| ERPNEXT_API_KEY | - | API key for authentication |
| ERPNEXT_API_SECRET | - | API secret for authentication |
| DEVICE_ID | SCALE-L01 | Scale device identifier |
| RAVEN_CHANNEL | iot-lab | Raven channel for notifications |
| SCALE_BACKEND | sensor_skill | Scale backend (keyboard/serial/simulator/sensor_skill) |
| SENSOR_SKILL_ID | scale_plant | Sensor Skill ID for scale config |
| SCALE_PORT | /dev/ttyUSB0 | Serial port for scale (fallback) |
| SCALE_BAUD | 9600 | Serial baud rate (fallback) |
| SCALE_MIN_WEIGHT | 0.5 | Minimum valid weight (kg) |
| SCALE_MAX_WEIGHT | 500 | Maximum valid weight (kg) |
| BARCODE_BACKEND | keyboard | Barcode backend (keyboard/camera) |
| FLASK_HOST | 0.0.0.0 | Flask bind host |
| FLASK_PORT | 5000 | Flask bind port |

## Backends

### Scale Backends

- **KeyboardBackend**: Type weight manually
- **SimulatorBackend**: Generate random weights (20-30 kg) for testing
- **SerialBackend**: STUB - read from Arduino/industrial scale via /dev/ttyUSB0
- **SensorSkillBackend**: **RECOMMENDED** - Reads from serial port using PH13.2.0 Sensor Skill config

### Sensor Skill Backend

The `sensor_skill` backend is recommended for production use. It fetches scale configuration from `amb_w_spc` Sensor Skill DocType:

**Available Sensor Skills:**
- `scale_plant`: Plant Production Scale (max 500kg, ModbusRTU, /dev/ttyUSB0)
- `scale_lab`: Laboratory Precision Scale (max 30kg, SerialCommand, /dev/ttyUSB1)

**Supported Drivers:**
- `ModbusRTU`: For industrial scales via RS485
- `SerialCommand`: For precision balances with command protocol

### Barcode Backends

- **KeyboardBarcodeBackend**: Type barrel serial manually
- **CameraBarcodeBackend**: STUB - scan with phone/RPi camera

## Barrel Serial Format

Valid format: `JAR0001261-1-C1-001`

Pattern: `[A-Z]{3}[0-9]+-[0-9]+-C[0-9]+-[0-9]+`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| / | GET | Main weight capture page |
| /api/submit-weight | POST | Submit barrel + weight |
| /api/barrels/\<serial\> | GET | Validate barrel serial |
| /api/read-weight | POST | Read weight from scale (sensor_skill backend) |
| /api/status | GET | Device status with Sensor Skill info |
| /api/pending | GET | List pending submissions |
| /api/retry-pending | POST | Retry pending submissions |
| /api/history | GET | Submission history |
| /api/cleanup-duplicates | POST | Remove duplicate entries |

## Offline Buffering

Failed submissions are stored in `weight_buffer.db` and retried automatically or via the menu.

## Troubleshooting

### Flask won't start

Check if port 5000 is available:
```bash
lsof -i :5000
```

### ngrok tunnel fails

Verify authtoken:
```bash
ngrok config add-authtoken <token>
```

### Scale not reading

For serial backend:
```bash
ls -l /dev/ttyUSB*
stty -F /dev/ttyUSB0 9600
```

## Files

```
rpi_client/
├── __init__.py
├── sensor_skill_client.py  # PH13.2.0 Sensor Skill config client
├── scale_reader.py       # Scale reading with backends
├── barcode_handler.py    # Barcode scanning
├── weight_capture_client.py  # Terminal client
├── web_app.py            # Flask web app
├── templates/
│   └── index.html        # Mobile UI
├── start_tunnel.sh       # Start ngrok only
├── start_all.sh          # Start all services
└── requirements.txt      # Python dependencies
```

## PH13.2.0 Requirements

For `sensor_skill` backend to work, ensure:

1. `amb_w_spc` v15+ is installed on ERPNext
2. Sensor Skill records exist in ERPNext:
   - `scale_plant`: Plant Production Scale
   - `scale_lab`: Laboratory Precision Scale
3. API credentials are configured (ERPNEXT_API_KEY, ERPNEXT_API_SECRET)
