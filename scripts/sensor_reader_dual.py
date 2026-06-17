import os, serial, json, time, math, requests, threading, glob
from datetime import datetime
from dotenv import load_dotenv

# Load credentials from rpi_client/.env (sandbox + working keys)
load_dotenv('/home/admin/raven-bot/rpi_client/.env')
ERPNEXT_URL = os.getenv('ERPNEXT_URL', 'https://sandbox.sysmayal.cloud').rstrip('/')
API_KEY = os.getenv('ERPNEXT_API_KEY', '')
API_SECRET = os.getenv('ERPNEXT_API_SECRET', '')
DEVICE_LABEL = os.getenv('DEVICE_LABEL', 'L01')

# Milestone 2 (2026-05-08): identity-based routing.
# Reader discovers sensors by reading the JSON each Arduino emits, matches it
# against a handler in HANDLERS (or — TODO M3 — looks up the skill in ERPNext).
# No more hardcoded port -> sensor type map. Ports come from the udev rules at
# /etc/udev/rules.d/99-raven-sensors.rules (raven-port-A..D, X, Y).
PORT_GLOB = '/dev/raven-port-*'
DEFAULT_BAUD = 9600
RESCAN_INTERVAL_S = 10  # how often the main loop looks for new symlinks (M4)
IDENTIFY_TIMEOUT_S = 30  # give up identifying a port after N seconds of garbage
STALL_TIMEOUT_S = 90          # watchdog: reconnect an identified sensor after this much silence (DTR-reset)
STALL_BACKOFF_BASE_S = 5      # backoff before reopen after a stall; doubles per consecutive stall
STALL_BACKOFF_MAX_S = 300     # cap so a dead sensor doesn't flap
HEALTHY_SESSION_S = 120       # a session lasting this long clears the stall backoff counter

# --- Ford NTC (216+1S7Z6G004AA) decoding -------------------------------------
R_PULLUP = 10000.0
SH_A = 3.7017258960e-03
SH_B = -2.7269109373e-04
SH_C = 3.6931214759e-06

def ford_ntc_to_temp(raw_adc):
    """Steinhart-Hart on a 5V -> 10K pullup -> A0 -> NTC -> GND divider."""
    if raw_adc <= 0 or raw_adc >= 1023:
        return None, None
    r_sensor = R_PULLUP * (float(raw_adc) / (1023.0 - float(raw_adc)))
    ln_r = math.log(r_sensor)
    inv_t = SH_A + SH_B * ln_r + SH_C * ln_r ** 3
    return round((1.0 / inv_t) - 273.15, 1), round(r_sensor, 0)

# --- ERPNext post -------------------------------------------------------------
def post_to_erpnext(data):
    try:
        headers = {
            'Authorization': f'token {API_KEY}:{API_SECRET}',
            'Content-Type': 'application/json',
        }
        r = requests.post(
            f'{ERPNEXT_URL}/api/resource/IoT Sensor Reading',
            headers=headers, json={'data': data}, timeout=10,
        )
        return r.status_code
    except Exception as e:
        print(f'  ERPNext error: {e}')
        return None

# --- Per-sensor handlers ------------------------------------------------------
# Each handler takes (json_dict, timestamp_str) -> reading dict (or None to skip).
# Reading dict gets device_name + timestamp filled in by the dispatcher.

def handle_ntc(d, ts):
    raw = d.get('raw', 0)
    temp_c, r_ohms = ford_ntc_to_temp(raw)
    if temp_c is None:
        return None
    return {
        'sensor_id': d.get('id', 'FORD-NTC-01'),
        'sensor_type': 'Ford Temperature',
        'temperature': temp_c,
        'resistance': r_ohms,
        'raw_adc': raw,
        'millivolts': d.get('mv', 0),
        'unit': 'C',
    }

def handle_dht11(d, ts):
    t, h = d.get('t'), d.get('h')
    if t is None or h is None:
        return None
    return {
        'sensor_id': d.get('id', 'DHT11-01'),
        'sensor_type': 'DHT11',
        'temperature': t,
        'humidity': h,
        'unit': 'C',
    }

def handle_soil(d, ts):
    return {
        'sensor_id': d.get('id', 'SOIL-01'),
        'sensor_type': 'Soil Moisture',
        'soil_moisture': d.get('sm', 0),
        'soil_dry': d.get('sd', 0),
    }

# Local handler registry. M3 will replace lookup_skill() with an ERPNext call
# against the Sensor Skill DocType — keep this file's surface stable.
HANDLERS = {
    'NTC':   handle_ntc,
    'DHT11': handle_dht11,
    'SOIL':  handle_soil,
}

def identify(d):
    """Return the sensor kind name from a JSON sample, or None if unknown.

    Priority: explicit `s` field from the firmware, then key-shape inference
    for legacy firmwares that don't include `s` (e.g. soil)."""
    s = d.get('s')
    if isinstance(s, str) and s.upper() in HANDLERS:
        return s.upper()
    if 'sm' in d:
        return 'SOIL'
    if 't' in d and 'h' in d and 'raw' not in d:
        return 'DHT11'
    if 'raw' in d and 'mv' in d:
        return 'NTC'
    return None

def lookup_skill(kind, sensor_id):
    """Skill registry hook. Today: local HANDLERS dict. M3: ERPNext lookup
    against the Sensor Skill DocType keyed on (kind, sensor_id) -> handler
    config (decoder, calibration, target DocType, polling rate, ...)."""
    return HANDLERS.get(kind)

# --- Per-port worker ----------------------------------------------------------
def reading_summary(kind, r):
    if kind == 'NTC':
        return f'Ford: {r.get("temperature")}C R={r.get("resistance")}ohm raw={r.get("raw_adc")}'
    if kind == 'DHT11':
        return f'DHT11: {r.get("temperature")}C {r.get("humidity")}%'
    if kind == 'SOIL':
        return f'Soil: sm={r.get("soil_moisture")} dry={r.get("soil_dry")}'
    return str(r)

def watch_port(port):
    """Open `port`, sniff first JSON line to identify the sensor, dispatch."""
    name = os.path.basename(port)
    print(f'[{name}] watcher started')
    absent = False
    stall_count = 0      # consecutive silent-stall recoveries (for exponential backoff)
    while True:
        if not os.path.exists(port):
            if not absent:
                print(f'[{name}] absent, polling every 60s')
                absent = True
            time.sleep(60)
            continue
        if absent:
            print(f'[{name}] reappeared')
            absent = False
        try:
            ser = serial.Serial(port, DEFAULT_BAUD, timeout=10)
            time.sleep(2)
            ser.flushInput()
            kind = None
            sensor_id = None
            handler = None
            id_started = time.time()
            session_start = time.time()
            last_emit = time.time()
            while True:
                line = ser.readline().decode(errors='ignore').strip()
                if not line:
                    if handler is None and time.time() - id_started > IDENTIFY_TIMEOUT_S:
                        print(f'[{name}] no JSON in {IDENTIFY_TIMEOUT_S}s, retrying')
                        break
                    if handler is not None and time.time() - last_emit > STALL_TIMEOUT_S:
                        stall_count += 1
                        backoff = min(STALL_BACKOFF_BASE_S * (2 ** (stall_count - 1)), STALL_BACKOFF_MAX_S)
                        print(f'[{name}] WATCHDOG: silent {STALL_TIMEOUT_S}s (stall #{stall_count}); '
                              f'close/reopen to DTR-reset, backoff {backoff}s')
                        try:
                            ser.close()
                        except Exception:
                            pass
                        time.sleep(backoff)
                        break
                    continue
                last_emit = time.time()
                if stall_count and time.time() - session_start > HEALTHY_SESSION_S:
                    print(f'[{name}] healthy {int(time.time() - session_start)}s, clearing stall backoff')
                    stall_count = 0
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if handler is None:
                    kind = identify(d)
                    sensor_id = d.get('id', kind or 'UNKNOWN')
                    handler = lookup_skill(kind, sensor_id)
                    if handler is None:
                        print(f'[{name}] unknown sensor JSON: {line[:80]}')
                        time.sleep(5)
                        break
                    print(f'[{name}] identified -> {kind} (id={sensor_id})')
                reading = handler(d, ts)
                if reading is None:
                    continue
                reading.setdefault('device_name', DEVICE_LABEL)
                reading.setdefault('timestamp', ts)
                print(f'[{name}] {reading_summary(kind, reading)}')
                status = post_to_erpnext(reading)
                print(f'  -> ERP: {status}')
        except serial.SerialException as e:
            print(f'[{name}] reconnecting... ({e})')
            time.sleep(5)
        except Exception as e:
            print(f'[{name}] error: {e}')
            time.sleep(5)

# --- Main: scan symlinks, launch one watcher thread per port ------------------
if __name__ == '__main__':
    print('=== Raven Sensor Reader (port-watch + JSON identify) ===')
    print(f'scanning {PORT_GLOB} every {RESCAN_INTERVAL_S}s')
    seen = set()
    try:
        while True:
            for port in sorted(glob.glob(PORT_GLOB)):
                if port in seen:
                    continue
                seen.add(port)
                threading.Thread(target=watch_port, args=(port,), daemon=True).start()
                print(f'launched watcher for {port}')
            time.sleep(RESCAN_INTERVAL_S)
    except KeyboardInterrupt:
        print('\nStopped.')
