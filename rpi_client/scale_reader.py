#!/usr/bin/env python3
"""Scale Reader Module with pluggable backends.

This module provides a unified interface for reading weight from different scale backends:
- KeyboardBackend: Operator types weight directly
- SerialBackend: Reads from serial port (with Sensor Skill config)
- SimulatorBackend: Generates random weights for testing

Integration with PH13.2.0:
    When using 'sensor_skill' backend, configuration is fetched from
    amb_w_spc's Sensor Skill DocType (scale_plant or scale_lab).

Usage:
    from scale_reader import ScaleReader, KeyboardBackend, SimulatorBackend

    reader = ScaleReader(backend='sensor_skill')  # Uses Sensor Skill config
    weight = reader.read_weight()
"""
import os
import sys
import time
import random
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

# Import Sensor Skill client for configuration
try:
    from sensor_skill_client import SensorSkillClient, SensorSkillError
    SENSOR_SKILL_AVAILABLE = True
except ImportError:
    SENSOR_SKILL_AVAILABLE = False
    SensorSkillClient = None
    SensorSkillError = None


class ScaleReaderError(Exception):
    """Base exception for scale reader errors."""
    pass


class ValidationError(ScaleReaderError):
    """Raised when weight validation fails."""
    pass


class ConnectionError(ScaleReaderError):
    """Raised when scale connection fails."""
    pass


class ScaleBackend(ABC):
    """Abstract base class for scale backends."""

    @abstractmethod
    def read_raw(self) -> Optional[float]:
        """Read raw weight value from the backend.

        Returns:
            Weight in kg, or None if reading failed.
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if the backend is connected and ready.

        Returns:
            True if connected, False otherwise.
        """
        pass

    def close(self):
        """Close the backend connection. Override if needed."""
        pass


class KeyboardBackend(ScaleBackend):
    """Keyboard/Terminal input backend.

    Reads weight from stdin where operator types the weight value.
    """

    def __init__(self, prompt: str = "Enter weight (kg): "):
        """Initialize keyboard backend.

        Args:
            prompt: Prompt string shown to operator.
        """
        self.prompt = prompt
        self._connected = True

    def read_raw(self) -> Optional[float]:
        """Read weight from stdin.

        Returns:
            Weight in kg as float, or None on error.
        """
        try:
            user_input = input(self.prompt).strip()
            if not user_input:
                return None
            return float(user_input)
        except ValueError:
            logger.error(f"Invalid weight format: {user_input}")
            return None
        except EOFError:
            return None

    def is_connected(self) -> bool:
        """Always returns True for keyboard backend."""
        return self._connected


class SerialBackend(ScaleBackend):
    """Serial port backend for reading from industrial scales.

    STUB: Basic structure for future implementation with Arduino Nano
    or industrial scale connected via /dev/ttyUSB0.
    """

    def __init__(self, port: str = None, baud: int = 9600,
                 timeout: float = 5.0):
        """Initialize serial backend.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0'). Defaults to env SCALE_PORT.
            baud: Baud rate. Defaults to 9600.
            timeout: Read timeout in seconds.
        """
        self.port = port or os.getenv('SCALE_PORT', '/dev/ttyUSB0')
        self.baud = baud
        self.timeout = timeout
        self._serial = None
        self._connected = False

    def connect(self) -> bool:
        """Establish serial connection.

        TODO: Implement actual serial connection using pyserial.
              For now, this is a STUB that always fails.

        Returns:
            True if connected, False otherwise.
        """
        # TODO: Implement serial connection
        # Example:
        # import serial
        # try:
        #     self._serial = serial.Serial(
        #         port=self.port,
        #         baudrate=self.baud,
        #         timeout=self.timeout
        #     )
        #     self._connected = True
        #     return True
        # except serial.SerialException as e:
        #     logger.error(f"Serial connection failed: {e}")
        #     return False
        logger.warning("SerialBackend.connect() - STUB: Not implemented")
        self._connected = False
        return False

    def read_raw(self) -> Optional[float]:
        """Read weight from serial port.

        TODO: Implement actual serial reading.
              Expected format may vary by scale manufacturer.

        Returns:
            Weight in kg, or None if reading failed.
        """
        # TODO: Implement serial reading
        # Example:
        # if not self._connected:
        #     self.connect()
        # if self._serial and self._serial.in_waiting:
        #     line = self._serial.readline().decode('utf-8').strip()
        #     # Parse weight from line based on scale protocol
        #     return float(parse_weight(line))
        logger.warning("SerialBackend.read_raw() - STUB: Not implemented")
        return None

    def is_connected(self) -> bool:
        """Check if serial port is connected."""
        return self._connected

    def close(self):
        """Close serial connection."""
        if self._serial:
            self._serial.close()
            self._serial = None
            self._connected = False


class SimulatorBackend(ScaleBackend):
    """Simulator backend for testing without hardware.

    Generates random weights in the range 20-30 kg.
    """

    def __init__(self, min_weight: float = 20.0, max_weight: float = 30.0):
        """Initialize simulator backend.

        Args:
            min_weight: Minimum weight in kg.
            max_weight: Maximum weight in kg.
        """
        self.min_weight = min_weight
        self.max_weight = max_weight
        self._connected = True

    def read_raw(self) -> Optional[float]:
        """Generate random weight.

        Returns:
            Random weight between min_weight and max_weight.
        """
        weight = random.uniform(self.min_weight, self.max_weight)
        return round(weight, 2)

    def is_connected(self) -> bool:
        """Always returns True for simulator."""
        return self._connected


class SensorSkillBackend(ScaleBackend):
    """Sensor Skill backend - reads from serial port using Sensor Skill config.

    This backend fetches scale configuration (port, baud_rate, python_config)
    from amb_w_spc's Sensor Skill DocType and uses it for serial communication.

    Supports ModbusRTU and SerialCommand drivers as defined in python_config.
    """

    def __init__(self, skill_id: str = None):
        """Initialize Sensor Skill backend.

        Args:
            skill_id: Sensor Skill ID to use. Defaults to SENSOR_SKILL_ID env var
                     or 'scale_plant'.
        """
        if not SENSOR_SKILL_AVAILABLE:
            logger.error("sensor_skill_client not available, falling back to serial")
            self._fallback = SerialBackend()
            return

        self.skill_id = skill_id or os.getenv('SENSOR_SKILL_ID', 'scale_plant')
        self._client = SensorSkillClient(skill_id=self.skill_id)
        self._config = None
        self._serial = None
        self._connected = False

        self._load_config()

    def _load_config(self):
        """Load configuration from Sensor Skill."""
        try:
            self._config = self._client.get_config()
            logger.info(f"Loaded Sensor Skill config: {self.skill_id}")
            logger.info(f"  Port: {self._config.get('port')}")
            logger.info(f"  Baud: {self._config.get('baud_rate')}")
            logger.info(f"  Driver: {self._config.get('python_config', {}).get('driver')}")
        except SensorSkillError as e:
            logger.error(f"Failed to load Sensor Skill config: {e}")
            self._config = {
                'port': '/dev/ttyUSB0',
                'baud_rate': 9600,
                'python_config': {'driver': 'ModbusRTU'},
                'max_value': 500,
                'min_value': 0,
            }

    def connect(self) -> bool:
        """Establish serial connection using Sensor Skill config.

        Returns:
            True if connected, False otherwise.
        """
        if not SENSOR_SKILL_AVAILABLE:
            return self._fallback.connect()

        try:
            import serial
            port = self._config.get('port', '/dev/ttyUSB0')
            baud = self._config.get('baud_rate', 9600)

            self._serial = serial.Serial(
                port=port,
                baudrate=baud,
                timeout=5.0
            )
            self._connected = True
            logger.info(f"Connected to {port} at {baud} baud")
            return True

        except Exception as e:
            logger.error(f"Serial connection failed: {e}")
            self._connected = False
            return False

    def read_raw(self) -> Optional[float]:
        """Read weight from serial port using Sensor Skill driver.

        Returns:
            Weight in kg, or None if reading failed.
        """
        if not SENSOR_SKILL_AVAILABLE:
            return self._fallback.read_raw()

        if not self._connected:
            self.connect()

        if not self._serial:
            return None

        try:
            python_config = self._config.get('python_config', {})
            driver = python_config.get('driver', 'ModbusRTU')

            if driver == 'ModbusRTU':
                return self._read_modbus()
            elif driver == 'SerialCommand':
                return self._read_serial_command()
            else:
                # Generic serial read
                return self._read_generic()

        except Exception as e:
            logger.error(f"Read error: {e}")
            return None

    def _read_modbus(self) -> Optional[float]:
        """Read weight using ModbusRTU protocol."""
        try:
            import minimalmodbus
            python_config = self._config.get('python_config', {})
            slave_id = python_config.get('slave_id', 1)
            scale_factor = python_config.get('scale_factor', 0.01)

            # Read from register 0 (weight)
            instrument = minimalmodbus.Instrument(
                self._config.get('port', '/dev/ttyUSB0'),
                slave_id
            )
            instrument.serial.baudrate = self._config.get('baud_rate', 9600)

            weight_raw = instrument.read_register(0, 0)
            weight = weight_raw * scale_factor

            return round(weight, 2)

        except Exception as e:
            logger.error(f"Modbus read error: {e}")
            return None

    def _read_serial_command(self) -> Optional[float]:
        """Read weight using SerialCommand protocol."""
        try:
            python_config = self._config.get('python_config', {})
            command = python_config.get('command', 'W')
            response_format = python_config.get('response_format', 'DECIMAL')

            # Send command
            self._serial.write(f"{command}\r\n".encode())
            time.sleep(0.5)

            # Read response
            if self._serial.in_waiting:
                line = self._serial.readline().decode('utf-8').strip()

                # Parse based on format
                if response_format == 'DECIMAL':
                    # Expect plain decimal number
                    return float(line)
                else:
                    # Try to extract number from response
                    import re
                    match = re.search(r'[-+]?\d*\.?\d+', line)
                    if match:
                        return float(match.group())

            return None

        except Exception as e:
            logger.error(f"Serial command read error: {e}")
            return None

    def _read_generic(self) -> Optional[float]:
        """Generic serial read - read line and try to parse weight."""
        try:
            if self._serial.in_waiting:
                line = self._serial.readline().decode('utf-8').strip()
                import re
                match = re.search(r'[-+]?\d*\.?\d+', line)
                if match:
                    return float(match.group())
            return None
        except Exception as e:
            logger.error(f"Generic read error: {e}")
            return None

    def is_connected(self) -> bool:
        """Check if serial port is connected."""
        if not SENSOR_SKILL_AVAILABLE:
            return self._fallback.is_connected()
        return self._connected

    def close(self):
        """Close serial connection."""
        if self._serial:
            self._serial.close()
            self._serial = None
            self._connected = False


class ScaleReader:
    """Main scale reader with stable reading detection and validation.

    Reads weight from a backend and validates:
    - Stability: 3 consecutive readings within 0.1 kg tolerance
    - Range: Between min_weight and max_weight (from Sensor Skill or env)

    Supports backends: 'keyboard', 'serial', 'simulator', 'sensor_skill'
    """

    def __init__(self, backend: str = None, skill_id: str = None):
        """Initialize scale reader with specified backend.

        Args:
            backend: Backend type ('keyboard', 'serial', 'simulator', 'sensor_skill').
                    Defaults to SCALE_BACKEND env var or 'keyboard'.
                    'sensor_skill' fetches config from amb_w_spc Sensor Skill DocType.
            skill_id: Sensor Skill ID to use (for 'sensor_skill' backend).
                    Defaults to SENSOR_SKILL_ID env var or 'scale_plant'.
        """
        self.backend_name = backend or os.getenv('SCALE_BACKEND', 'keyboard')
        self.skill_id = skill_id or os.getenv('SENSOR_SKILL_ID', 'scale_plant')

        # Load min/max from Sensor Skill if using sensor_skill backend
        if self.backend_name == 'sensor_skill' and SENSOR_SKILL_AVAILABLE:
            try:
                client = SensorSkillClient(skill_id=self.skill_id)
                config = client.get_config()
                self.min_weight = float(config.get('min_value', 0.5))
                self.max_weight = float(config.get('max_value', 500))
                logger.info(f"Loaded weight range from Sensor Skill: "
                           f"{self.min_weight}-{self.max_weight} kg")
            except SensorSkillError as e:
                logger.warning(f"Failed to load Sensor Skill config: {e}")
                self.min_weight = float(os.getenv('SCALE_MIN_WEIGHT', '0.5'))
                self.max_weight = float(os.getenv('SCALE_MAX_WEIGHT', '500'))
        else:
            self.min_weight = float(os.getenv('SCALE_MIN_WEIGHT', '0.5'))
            self.max_weight = float(os.getenv('SCALE_MAX_WEIGHT', '500'))

        self.stability_tolerance = 0.1
        self.stability_readings = 3

        self._backend = self._create_backend()

    def _create_backend(self) -> ScaleBackend:
        """Create the appropriate backend instance.

        Returns:
            ScaleBackend instance.
        """
        if self.backend_name == 'simulator':
            return SimulatorBackend()
        elif self.backend_name == 'serial':
            port = os.getenv('SCALE_PORT', '/dev/ttyUSB0')
            baud = int(os.getenv('SCALE_BAUD', '9600'))
            return SerialBackend(port=port, baud=baud)
        elif self.backend_name == 'sensor_skill':
            return SensorSkillBackend(skill_id=self.skill_id)
        else:
            return KeyboardBackend()

    def _validate_weight(self, weight: float) -> bool:
        """Validate weight is within acceptable range.

        Args:
            weight: Weight in kg.

        Returns:
            True if valid, False otherwise.
        """
        if weight < self.min_weight:
            logger.error(f"Weight {weight} below minimum {self.min_weight} kg")
            return False
        if weight > self.max_weight:
            logger.error(f"Weight {weight} above maximum {self.max_weight} kg")
            return False
        return True

    def _is_stable(self, readings: list) -> bool:
        """Check if readings are stable within tolerance.

        Args:
            readings: List of weight readings.

        Returns:
            True if all readings within tolerance of first reading.
        """
        if len(readings) < self.stability_readings:
            return False

        first = readings[0]
        return all(abs(r - first) <= self.stability_tolerance for r in readings)

    def read_weight(self) -> float:
        """Read and validate stable weight.

        Waits for 3 consecutive stable readings before returning.
        Automatically validates weight range.

        Returns:
            Stable weight in kg.

        Raises:
            ValidationError: If weight is out of range.
            ScaleReaderError: If unable to get stable reading.
        """
        readings = []
        max_attempts = 20

        logger.info(f"Reading weight from {self.backend_name} backend...")

        for attempt in range(max_attempts):
            raw = self._backend.read_raw()

            if raw is None:
                logger.warning(f"Attempt {attempt + 1}: No reading received")
                time.sleep(0.5)
                continue

            if not self._validate_weight(raw):
                logger.warning(f"Attempt {attempt + 1}: Invalid weight {raw} kg")
                continue

            readings.append(raw)
            logger.debug(f"Attempt {attempt + 1}: Reading {raw} kg (buffer: {readings})")

            if self._is_stable(readings):
                final_weight = round(readings[-1], 2)
                logger.info(f"Stable weight confirmed: {final_weight} kg")
                return final_weight

        raise ScaleReaderError(
            f"Could not get stable reading after {max_attempts} attempts. "
            f"Last readings: {readings[-3:] if readings else []}"
        )

    def is_connected(self) -> bool:
        """Check if the backend is connected.

        Returns:
            True if connected, False otherwise.
        """
        return self._backend.is_connected()

    def close(self):
        """Close the backend connection."""
        self._backend.close()


def main():
    """Command-line interface for testing the scale reader."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    parser = argparse.ArgumentParser(description='Scale Reader Test')
    parser.add_argument(
        '--backend', '-b',
        choices=['keyboard', 'serial', 'simulator'],
        default=os.getenv('SCALE_BACKEND', 'simulator'),
        help='Scale backend to use'
    )
    parser.add_argument(
        '--count', '-c',
        type=int,
        default=1,
        help='Number of readings to take'
    )

    args = parser.parse_args()

    print(f"=== Scale Reader Test ===")
    print(f"Backend: {args.backend}")
    print(f"Min/Max: {os.getenv('SCALE_MIN_WEIGHT', '0.5')} - "
          f"{os.getenv('SCALE_MAX_WEIGHT', '500')} kg")
    print()

    reader = ScaleReader(backend=args.backend)

    for i in range(args.count):
        print(f"\n--- Reading {i + 1} ---")
        try:
            weight = reader.read_weight()
            print(f"SUCCESS: {weight} kg")
        except ScaleReaderError as e:
            print(f"ERROR: {e}")

    reader.close()


if __name__ == '__main__':
    main()
