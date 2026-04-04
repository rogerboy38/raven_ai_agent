#!/usr/bin/env python3
"""
Serial Port Sniffer - Auto-detect scale on any port
==================================================
Sniffs all serial ports and detects:
- Active data streams
- Data format (ModbusRTU, plain text, etc.)
- Updates Sensor Skill config automatically

Run: python3 port_sniffer.py [--port /dev/ttyUSB3]
"""
import sys
import os
import time
import argparse
import threading
from collections import defaultdict

# Check pyserial
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("ERROR: pyserial not installed")
    print("Install with: pip install pyserial")
    sys.exit(1)


class SerialSniffer:
    """Sniffs serial ports to detect scale devices."""

    def __init__(self, ports=None, timeout=2.0, samples=10):
        self.ports = ports or self._list_all_ports()
        self.timeout = timeout
        self.samples = samples
        self.results = defaultdict(dict)
        self.running = False

    def _list_all_ports(self):
        """List all available serial ports."""
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append(port.device)
        return ports

    def _is_modbus_rtu(self, data: bytes) -> bool:
        """Check if data looks like ModbusRTU."""
        if len(data) < 5:
            return False
        # ModbusRTU format: [slave_id][function][data...][crc_low][crc_high]
        # Common function codes: 0x03 (read), 0x04 (read input)
        return data[1] in [0x03, 0x04, 0x06, 0x10] and len(data) >= 5

    def _parse_weight_from_modbus(self, data: bytes) -> float:
        """Extract weight from ModbusRTU response."""
        try:
            if len(data) >= 6 and data[1] in [0x03, 0x04]:
                # Register value is in bytes 3-4 (big endian)
                raw = (data[3] << 8) | data[4]
                # Apply scale factor (typically 0.01 for kg)
                weight = raw * 0.01
                return weight
        except:
            pass
        return None

    def _parse_weight_from_text(self, data: str) -> float:
        """Extract weight from plain text data."""
        import re
        # Look for decimal number pattern
        match = re.search(r'[-+]?\d*\.?\d+', data)
        if match:
            try:
                return float(match.group())
            except:
                pass
        return None

    def _analyze_port(self, port: str) -> dict:
        """Analyze a single port for activity and data format."""
        result = {
            'port': port,
            'active': False,
            'data_samples': [],
            'format': None,
            'suggested_driver': None,
            'suggested_config': {},
        }

        try:
            ser = serial.Serial(
                port=port,
                baudrate=9600,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout
            )

            print(f"  Checking {port}...", end=" ", flush=True)

            samples = []
            start_time = time.time()

            while time.time() - start_time < self.timeout:
                if ser.in_waiting:
                    result['active'] = True
                    data = ser.read(ser.in_waiting)
                    samples.append(data)

                    # Try to parse
                    if self._is_modbus_rtu(data):
                        result['format'] = 'ModbusRTU'
                        weight = self._parse_weight_from_modbus(data)
                        if weight:
                            samples.append(f" -> Weight: {weight:.3f} kg")
                    else:
                        # Try as text
                        try:
                            text = data.decode('utf-8', errors='ignore').strip()
                            if text:
                                result['format'] = 'PlainText'
                                weight = self._parse_weight_from_text(text)
                                if weight:
                                    samples.append(f" -> Weight: {weight:.3f} kg")
                                else:
                                    samples.append(f" -> Data: {text[:50]}")
                        except:
                            result['format'] = 'Binary'
                            samples.append(f" -> Binary: {data.hex()[:30]}...")

                time.sleep(0.1)

            ser.close()

            if result['active']:
                result['data_samples'] = samples

                # Suggest configuration
                if result['format'] == 'ModbusRTU':
                    result['suggested_driver'] = 'ModbusRTU'
                    result['suggested_config'] = {
                        'slave_id': 1,
                        'scale_factor': 0.01,
                    }
                elif result['format'] == 'PlainText':
                    result['suggested_driver'] = 'SerialCommand'
                    result['suggested_config'] = {
                        'command': 'W',
                        'response_format': 'DECIMAL',
                    }
                else:
                    result['suggested_driver'] = 'Generic'
                    result['suggested_config'] = {}

                print(f"ACTIVE - {result['format']}")
                for sample in samples[:3]:
                    print(f"    {sample}")
            else:
                print("No activity")

        except serial.SerialException as e:
            result['error'] = str(e)
            print(f"Error: {e}")
        except Exception as e:
            result['error'] = str(e)
            print(f"Error: {e}")

        return result

    def sniff(self) -> dict:
        """Sniff all ports and return results."""
        print("=" * 60)
        print("SERIAL PORT SNIFFER")
        print("=" * 60)
        print(f"Scanning {len(self.ports)} ports...")
        print()

        for port in self.ports:
            self.results[port] = self._analyze_port(port)

        print()
        print("=" * 60)
        print("ANALYSIS COMPLETE")
        print("=" * 60)

        # Summary
        active_ports = [p for p, r in self.results.items() if r.get('active')]
        if active_ports:
            print(f"\nActive ports found: {len(active_ports)}")
            for port in active_ports:
                r = self.results[port]
                print(f"  {port}:")
                print(f"    Format: {r.get('format')}")
                print(f"    Driver: {r.get('suggested_driver')}")
                print(f"    Config: {r.get('suggested_config')}")
        else:
            print("\nNo active scale devices detected.")
            print("Make sure the scale is connected and transmitting data.")

        return self.results

    def get_best_port(self) -> dict:
        """Get the port most likely to be a scale."""
        for port, result in self.results.items():
            if result.get('active') and result.get('suggested_driver'):
                return result
        return None


def main():
    parser = argparse.ArgumentParser(description='Serial Port Sniffer')
    parser.add_argument('--port', '-p', help='Specific port to check')
    parser.add_argument('--timeout', '-t', type=float, default=3.0,
                        help='Timeout per port (seconds)')
    parser.add_argument('--samples', '-s', type=int, default=10,
                        help='Number of samples to collect')
    args = parser.parse_args()

    ports = [args.port] if args.port else None

    sniffer = SerialSniffer(ports=ports, timeout=args.timeout, samples=args.samples)
    results = sniffer.sniff()

    # Suggest action
    best = sniffer.get_best_port()
    if best:
        print("\n" + "=" * 60)
        print("RECOMMENDED ACTION")
        print("=" * 60)
        print(f"\nUpdate Sensor Skill with these settings:")
        print(f"  Port: {best['port']}")
        print(f"  Driver: {best['suggested_driver']}")
        print(f"  Config: {best['suggested_config']}")
        print()
        print("On server, run:")
        print(f"  doc = frappe.get_doc('Sensor Skill', 'scale_plant')")
        print(f"  doc.port = '{best['port']}'")
        if best['suggested_config']:
            import json
            doc_config = json.dumps(best['suggested_config'])
            print(f"  doc.python_config = '{doc_config}'")
        print("  doc.save()")
        print("  frappe.db.commit()")


if __name__ == "__main__":
    main()
