#!/usr/bin/env python3
"""
Dummy Scale Simulator - Outputs ModbusRTU-like weight data to serial port.
Used for testing without actual scale hardware.

Usage:
    python3 dummy_scale.py /dev/ttyUSB0 9600

This script continuously outputs weight readings in a format compatible
with the SensorSkillBackend's ModbusRTU driver.
"""
import sys
import time
import random
import threading

# Check if pyserial is available
try:
    import serial
except ImportError:
    print("ERROR: pyserial not installed")
    print("Install with: pip install pyserial")
    sys.exit(1)


class DummyScale:
    """Simulates a ModbusRTU scale device."""

    def __init__(self, port, baudrate=9600, base_weight=25.0):
        self.port = port
        self.baudrate = baudrate
        self.base_weight = base_weight
        self.current_weight = base_weight
        self.ser = None
        self.running = False

    def connect(self):
        """Open serial connection."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            print(f"Connected to {self.port} at {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            print(f"Failed to open {self.port}: {e}")
            return False

    def generate_weight_reading(self):
        """Generate a realistic weight reading with small variations."""
        # Add small random fluctuation (±0.1kg)
        variation = random.uniform(-0.1, 0.1)
        self.current_weight = self.base_weight + variation

        # Ensure weight stays in valid range
        self.current_weight = max(0, min(500, self.current_weight))

        return self.current_weight

    def format_modbus_response(self, weight):
        """Format weight as ModbusRTU register response.

        Modbus format for holding registers:
        [SlaveID] [FunctionCode] [ByteCount] [Data...] [CRC16]
        """
        # Weight in grams for Modbus register (scale_factor: 0.01 = grams)
        weight_grams = int(weight * 1000)  # Convert kg to grams

        # High and low bytes of register value
        high_byte = (weight_grams >> 8) & 0xFF
        low_byte = weight_grams & 0xFF

        # Simple response: slave_id=1, function=3 (read holding registers)
        # Register 0 = weight
        response = bytes([
            0x01,        # Slave ID
            0x03,        # Function code (read holding registers)
            0x02,        # Byte count
            high_byte,   # Weight high
            low_byte,    # Weight low
        ])

        # Calculate CRC16 (simplified)
        crc = self._crc16(response)
        response += bytes([crc & 0xFF, (crc >> 8) & 0xFF])

        return response

    def _crc16(self, data):
        """Calculate CRC16-MODBUS."""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

    def send_reading(self):
        """Send one weight reading."""
        weight = self.generate_weight_reading()
        response = self.format_modbus_response(weight)

        print(f"Sending: {weight:.3f} kg -> {response.hex()}")

        if self.ser and self.ser.is_open:
            self.ser.write(response)

    def run(self, interval=2.0):
        """Run the dummy scale loop."""
        if not self.connect():
            return

        self.running = True
        print(f"Sending weight readings every {interval} seconds...")
        print("Press Ctrl+C to stop")

        try:
            while self.running:
                self.send_reading()
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            self.close()

    def close(self):
        """Close serial connection."""
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Serial port closed")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 dummy_scale.py <port> [baudrate] [base_weight]")
        print("Example: python3 dummy_scale.py /dev/ttyUSB0 9600 25.5")
        print("         python3 dummy_scale.py COM3 9600 30.0")
        sys.exit(1)

    port = sys.argv[1]
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 9600
    base_weight = float(sys.argv[3]) if len(sys.argv) > 3 else 25.0

    scale = DummyScale(port, baudrate, base_weight)
    scale.run()


if __name__ == "__main__":
    main()
