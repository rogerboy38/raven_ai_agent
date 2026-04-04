#!/usr/bin/env python3
"""
Scale Reader Diagnostic Tester
==============================
Tests each component of the scale reading pipeline to identify where data is lost.

Run: python3 tester.py
"""
import sys
import os

# Add rpi_client to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("SCALE READER DIAGNOSTIC TESTER")
print("=" * 60)

# Test 1: Import sensor_skill_client
print("\n[TEST 1] Importing sensor_skill_client...")
try:
    from sensor_skill_client import SensorSkillClient, SENSOR_SKILL_AVAILABLE
    print(f"  SENSOR_SKILL_AVAILABLE = {SENSOR_SKILL_AVAILABLE}")
    print("  PASS: sensor_skill_client imported")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 2: Get sensor config from API
print("\n[TEST 2] Fetching Sensor Skill config...")
try:
    client = SensorSkillClient(skill_id='scale_plant')
    config = client.get_config()
    print(f"  Port: {config.get('port')}")
    print(f"  Baud Rate: {config.get('baud_rate')}")
    print(f"  Max Value: {config.get('max_value')}")
    driver = config.get('python_config', {}).get('driver', 'N/A')
    print(f"  Driver: {driver}")
    print("  PASS: Config fetched successfully")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 3: Import scale_reader
print("\n[TEST 3] Importing scale_reader...")
try:
    from scale_reader import ScaleReader, ScaleReaderError
    print("  PASS: scale_reader imported")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 4: Create ScaleReader instance
print("\n[TEST 4] Creating ScaleReader instance...")
try:
    reader = ScaleReader(backend='sensor_skill', skill_id='scale_plant')
    print(f"  backend_name: {reader.backend_name}")
    print(f"  skill_id: {reader.skill_id}")
    print("  PASS: ScaleReader created")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 5: Check connection
print("\n[TEST 5] Checking scale connection...")
try:
    is_connected = reader.is_connected()
    print(f"  is_connected() = {is_connected}")
    if is_connected:
        print("  PASS: Scale is connected")
    else:
        print("  WARN: Scale not connected (check port/baudrate)")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 6: Read weight
print("\n[TEST 6] Reading weight from scale...")
try:
    weight = reader.read_weight()
    print(f"  Weight: {weight} kg")
    print("  PASS: Weight read successfully")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 7: Close connection
print("\n[TEST 7] Closing connection...")
try:
    reader.close()
    print("  PASS: Connection closed")
except Exception as e:
    print(f"  FAIL: {e}")

# Test 8: Test with simulator backend
print("\n[TEST 8] Testing with simulator backend...")
try:
    sim_reader = ScaleReader(backend='simulator', skill_id='scale_plant')
    print(f"  is_connected() = {sim_reader.is_connected()}")
    weight = sim_reader.read_weight()
    print(f"  Weight: {weight} kg")
    sim_reader.close()
    print("  PASS: Simulator works")
except Exception as e:
    print(f"  FAIL: {e}")

# Summary
print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
print("\nIf any test shows FAIL, check the error message above.")
print("\nCommon issues and fixes:")
print("  1. 'No module named minimalmodbus':")
print("     pip install minimalmodbus")
print("")
print("  2. 'API credentials not configured':")
print("     Set ERPNEXT_URL, ERPNEXT_API_KEY, ERPNEXT_API_SECRET in .env")
print("")
print("  3. 'Port /dev/ttyUSB0 not found':")
print("     Update Sensor Skill port on server: bench console")
print("     doc = frappe.get_doc('Sensor Skill', 'scale_plant')")
print("     doc.port = '/dev/ttyUSB3'")
print("     doc.save()")
print("")
print("  4. Scale not connected:")
print("     - Check USB cable")
print("     - Verify port matches Sensor Skill config")
print("     - Try different port (ttyUSB0, ttyUSB1, etc.)")
