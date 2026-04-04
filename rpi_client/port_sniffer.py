#!/usr/bin/env python3
"""
Serial Port Sniffer - Intelligent Device Detection
==================================================
Detects serial devices and their data format:
- Scale weight data (ModbusRTU, plain text)
- Temperature sensors (DS18B20, DHT, etc.)
- Generic serial devices

Features:
- Hardware presence detection (DTR/RTS signals)
- Multi-baud rate scanning
- Temperature sensor detection
- Auto-config suggestions
- Port status overview

Run: python3 port_sniffer.py [--port /dev/ttyUSB3] [--verbose]
"""
import sys
import os
import time
import re
import json
import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

# Check pyserial
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("ERROR: pyserial not installed")
    print("Install with: pip install pyserial")
    sys.exit(1)


@dataclass
class PortInfo:
    """Information about a serial port."""
    device: str
    description: str = ""
    hwid: str = ""
    location: str = ""

    # Hardware status
    connected: bool = False
    signals: Dict[str, bool] = field(default_factory=dict)

    # Data detection
    has_data: bool = False
    bytes_available: int = 0
    data_samples: List[str] = field(default_factory=list)
    format_type: Optional[str] = None

    # Device detection
    device_type: Optional[str] = None
    suggested_driver: Optional[str] = None
    suggested_config: Dict[str, Any] = field(default_factory=dict)

    # Error if any
    error: Optional[str] = None


class IntelligentPortSniffer:
    """Intelligently sniffs serial ports for devices and data."""

    # Common baud rates to try
    BAUD_RATES = [9600, 19200, 38400, 57600, 115200, 2400, 4800]

    # Temperature sensor patterns
    TEMP_PATTERNS = [
        (r'(\d+\.\d+)\s*[°°C]', 'celsius'),
        (r'(\d+\.\d+)\s*[°°F]', 'fahrenheit'),
        (r'Temp[:\s]+(\d+\.\d+)', 'celsius'),
        (r't=(\d+)', 'raw_celsius'),
        (r'T=(\d+\.\d+)', 'celsius'),
        (r'(\d{2}:\d{2}:\d{2})', 'time'),
    ]

    # Weight patterns
    WEIGHT_PATTERNS = [
        (r'(\d+\.?\d*)\s*(?:kg|KG|Kg)', 'kg'),
        (r'(\d+\.?\d*)\s*(?:g|g\b)', 'grams'),
        (r'S\s*W[:\s]+(\d+\.?\d*)', 'stable_weight'),
        (r'W[:\s]+(\d+\.?\d*)', 'weight'),
        (r's(\d+)', 'scale_value'),
    ]

    def __init__(self, ports=None, timeout=2.0, verbose=False):
        self.timeout = timeout
        self.verbose = verbose
        self.ports = ports or self._list_all_ports()
        self.results: Dict[str, PortInfo] = {}

    def _list_all_ports(self) -> List[str]:
        """List all available serial ports with info."""
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append(port.device)
        return sorted(ports)

    def _get_port_info(self, port_name: str) -> PortInfo:
        """Get detailed info about a port."""
        info = PortInfo(device=port_name)

        try:
            port_details = None
            for p in serial.tools.list_ports.comports():
                if p.device == port_name:
                    port_details = p
                    break

            if port_details:
                info.description = port_details.description or "Unknown"
                info.hwid = port_details.hwid or "Unknown"
                info.location = port_details.location or "Unknown"

        except Exception as e:
            pass

        return info

    def _detect_device_type(self, samples: List[str]) -> Optional[str]:
        """Detect what type of device is connected."""
        text = ' '.join(samples).lower()

        # Temperature indicators
        if any(kw in text for kw in ['temp', 't=', 'humidity', 'hum', 'celsius', 'fahrenheit']):
            return 'temperature_sensor'

        # Scale/weight indicators
        if any(kw in text for kw in ['kg', 'weight', 'scale', 'balance', 'gram']):
            return 'scale'

        # GPS indicators
        if any(kw in text for kw in ['$gpgll', '$gprmc', 'gps', 'latitude', 'longitude']):
            return 'gps'

        # Generic serial device
        return 'unknown'

    def _parse_data_format(self, data: bytes) -> tuple:
        """Parse data and determine format."""
        # Try ModbusRTU
        if self._is_modbus_rtu(data):
            weight = self._parse_modbus_weight(data)
            return 'modbus_rtu', f"Weight: {weight:.3f} kg" if weight else "Modbus data"

        # Try plain text
        try:
            text = data.decode('utf-8', errors='ignore').strip()
            if text:
                # Check for temperature
                for pattern, unit in self.TEMP_PATTERNS:
                    match = re.search(pattern, text)
                    if match:
                        return 'temperature', f"{match.group(1)} {unit}"

                # Check for weight
                for pattern, unit in self.WEIGHT_PATTERNS:
                    match = re.search(pattern, text)
                    if match:
                        return 'weight', f"{match.group(1)} {unit}"

                return 'plain_text', text[:60]
        except:
            pass

        # Binary data
        return 'binary', data.hex()[:40]

    def _is_modbus_rtu(self, data: bytes) -> bool:
        """Check if data is ModbusRTU."""
        if len(data) < 5:
            return False
        # Check function code
        if data[1] in [0x03, 0x04, 0x06, 0x10]:
            return True
        return False

    def _parse_modbus_weight(self, data: bytes) -> Optional[float]:
        """Extract weight from Modbus response."""
        try:
            if len(data) >= 6 and data[1] in [0x03, 0x04]:
                raw = (data[3] << 8) | data[4]
                return raw * 0.01
        except:
            pass
        return None

    def _check_hardware_signals(self, ser: serial.Serial) -> Dict[str, bool]:
        """Check hardware signals on port."""
        signals = {}
        try:
            signals['dtr'] = ser.dtr
            signals['rts'] = ser.rts
            signals['cts'] = ser.cts
            signals['dsr'] = ser.dsr
            signals['ri'] = ser.ri
            signals['cd'] = ser.cd
        except:
            pass
        return signals

    def _probe_port(self, port_name: str, baudrate: int = 9600) -> PortInfo:
        """Probe a port for device and data."""
        info = self._get_port_info(port_name)

        try:
            # Open port
            ser = serial.Serial(
                port=port_name,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=1.0
            )

            info.connected = True
            info.signals = self._check_hardware_signals(ser)

            print(f"  {port_name:<15} [{baudrate} baud] ", end="", flush=True)

            # Check bytes in buffer
            info.bytes_available = ser.in_waiting

            if info.bytes_available > 0:
                info.has_data = True
                print(f"DATA ({info.bytes_available} bytes)", end="")
            else:
                print("No data     ", end="")

            # Hardware status
            if info.signals.get('dtr') or info.signals.get('rts'):
                print(" [HW DETECTED]", end="")

            # Try to read data
            samples = []
            start_time = time.time()
            max_samples = 10
            sample_count = 0

            while time.time() - start_time < self.timeout and sample_count < max_samples:
                if ser.in_waiting:
                    data = ser.read(ser.in_waiting)
                    if data:
                        info.has_data = True
                        fmt, parsed = self._parse_data_format(data)

                        if info.format_type is None:
                            info.format_type = fmt

                        samples.append(parsed)
                        print(f"\n    └─ {parsed[:60]}", end="")
                        sample_count += 1
                time.sleep(0.1)

            info.data_samples = samples

            # Detect device type from samples
            if samples:
                info.device_type = self._detect_device_type(samples)

                # Set suggested config based on type
                if info.format_type == 'modbus_rtu':
                    info.suggested_driver = 'ModbusRTU'
                    info.suggested_config = {'slave_id': 1, 'scale_factor': 0.01}
                elif info.device_type == 'temperature_sensor':
                    info.suggested_driver = 'TemperatureSensor'
                    info.suggested_config = {'poll_interval': 60, 'unit': 'celsius'}
                elif info.format_type in ['weight', 'plain_text']:
                    info.suggested_driver = 'SerialCommand'
                    info.suggested_config = {'command': 'W', 'response_format': 'DECIMAL'}
                else:
                    info.suggested_driver = 'GenericSerial'
                    info.suggested_config = {}

            print()
            ser.close()

        except serial.SerialException as e:
            info.error = str(e)
            print(f"  {port_name:<15} ERROR: {e}")
        except Exception as e:
            info.error = str(e)
            print(f"  {port_name:<15} ERROR: {e}")

        return info

    def sniff(self) -> Dict[str, PortInfo]:
        """Scan all ports and detect devices."""
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║           SERIAL PORT SNIFFER - Intelligent Mode             ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()
        print(f"  Timeout: {self.timeout}s | Baud rates: {self.BAUD_RATES}")
        print(f"  Ports to scan: {len(self.ports)}")
        print()
        print("─" * 65)

        for port in self.ports:
            info = self._probe_port(port)
            self.results[port] = info

        print("─" * 65)

        return self.results

    def print_summary(self):
        """Print intelligent summary."""
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║                     ANALYSIS SUMMARY                          ║")
        print("╚══════════════════════════════════════════════════════════════╝")

        # Categorize ports
        has_data = [p for p, i in self.results.items() if i.has_data]
        no_data = [p for p, i in self.results.items() if not i.has_data and i.connected]
        errors = [p for p, i in self.results.items() if i.error]

        # Check for specific device types
        scales = [p for p, i in self.results.items() if i.device_type == 'scale']
        temps = [p for p, i in self.results.items() if i.device_type == 'temperature_sensor']

        print()

        if has_data:
            print("  📊 PORTS WITH ACTIVE DATA:")
            print()
            for port in has_data:
                info = self.results[port]
                print(f"    ✓ {port}")
                print(f"      └─ Type: {info.device_type or info.format_type or 'Unknown'}")
                print(f"      └─ Format: {info.format_type}")
                print(f"      └─ Driver: {info.suggested_driver}")
                if info.data_samples:
                    print(f"      └─ Sample: {info.data_samples[0][:50]}")
                print()
        else:
            print("  ⚠️  NO ACTIVE DATA DETECTED")
            print()

            if no_data:
                print("  Ports with hardware present but no data:")
                for port in no_data:
                    info = self.results[port]
                    signals = info.signals
                    hw_status = []
                    if signals.get('dtr'): hw_status.append("DTR")
                    if signals.get('rts'): hw_status.append("RTS")
                    status = ", ".join(hw_status) if hw_status else "No signals"
                    print(f"    • {port}: {status}")
                print()

                print("  Possible reasons:")
                print("    1. Device not configured to output data")
                print("    2. Wrong baud rate (try different speed)")
                print("    3. Device needs to be polled first")
                print("    4. Scale is in 'hold' mode, press a button")
                print()

        if errors:
            print("  ❌ PORTS WITH ERRORS:")
            for port in errors:
                print(f"    • {port}: {self.results[port].error}")
            print()

        # Recommendations
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║                    RECOMMENDATIONS                            ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()

        if scales:
            print(f"  🔧 Found SCALE on: {', '.join(scales)}")
            print()
            print("  To configure:")
            for port in scales:
                info = self.results[port]
                if info.suggested_config:
                    print(f"    doc = frappe.get_doc('Sensor Skill', 'scale_plant')")
                    print(f"    doc.port = '{port}'")
                    if info.suggested_driver == 'ModbusRTU':
                        print(f"    doc.driver = 'ModbusRTU'")
                    else:
                        print(f"    doc.driver = 'SerialCommand'")
                    print(f"    doc.python_config = '{json.dumps(info.suggested_config)}'")
                    print(f"    doc.save(); frappe.db.commit()")
            print()

        if temps:
            print(f"  🌡️  Found TEMPERATURE SENSOR on: {', '.join(temps)}")
            print()

        if not has_data and not scales and not temps:
            print("  📝 NEXT STEPS:")
            print()
            print("    1. Connect your scale to a USB port")
            print("    2. Make sure scale is powered ON")
            print("    3. Check scale is set to 'transmit' or 'continuous' mode")
            print("    4. Re-run: python3 rpi_client/port_sniffer.py")
            print()
            print("    For testing without real scale, use simulator:")
            print("    python3 rpi_client/tester.py --mode simulator")
            print()

        print("─" * 65)

    def get_best_scale_port(self) -> Optional[PortInfo]:
        """Get the best port for a scale."""
        for port, info in self.results.items():
            if info.device_type == 'scale' and info.has_data:
                return info
        # Fallback to any port with data
        for port, info in self.results.items():
            if info.has_data:
                return info
        return None


def main():
    parser = argparse.ArgumentParser(
        description='Intelligent Serial Port Sniffer',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 port_sniffer.py                    # Scan all ports
  python3 port_sniffer.py --port /dev/ttyUSB3  # Scan specific port
  python3 port_sniffer.py --timeout 5        # Longer timeout
  python3 port_sniffer.py --verbose          # Verbose output
        """
    )
    parser.add_argument('--port', '-p', help='Specific port to check')
    parser.add_argument('--timeout', '-t', type=float, default=2.0,
                       help='Timeout per port (seconds, default: 2)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    args = parser.parse_args()

    ports = [args.port] if args.port else None

    sniffer = IntelligentPortSniffer(ports=ports, timeout=args.timeout, verbose=args.verbose)
    results = sniffer.sniff()
    sniffer.print_summary()

    # Auto-generate update script if scale found
    best = sniffer.get_best_scale_port()
    if best:
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║                 AUTO-GENERATE SCRIPT                         ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()
        print("Run this on your ERPNext server:")
        print()
        print("```python")
        print("import frappe")
        print("import json")
        print()
        print(f"doc = frappe.get_doc('Sensor Skill', 'scale_plant')")
        print(f"doc.port = '{best.port}'")
        print(f"doc.driver = '{best.suggested_driver}'")
        print(f"doc.python_config = '{json.dumps(best.suggested_config)}'")
        print("doc.save()")
        print("frappe.db.commit()")
        print("print('Updated!')")
        print("```")


if __name__ == "__main__":
    main()
