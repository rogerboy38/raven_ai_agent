# -*- coding: utf-8 -*-
"""
raven_ai_agent v0.3 — Seed Sensor Skill records for bot-iot-l01 testbed + production scale fleet
=================================================================================================

This is an idempotent seed patch (same pattern as amb_w_spc.patches.v15.04_create_sensor_skills_idempotent).
It populates the "Sensor Skill" DocType (owned by amb_w_spc / System Integration module) with:

PRODUCTION SCALE FLEET (placeholders, enabled=0 — tune per-scale when hardware is connected):
  - scale_juice       — Juice Plant endpoint, 0.010 kg precision
  - scale_dry         — Dry Plant endpoint, 0.010 kg precision
  - scale_mix         — Mix Plant endpoint, 0.010 kg precision
  - scale_formulated  — Formulated Plant endpoint, 0.010 kg precision
  - scale_lab         — Laboratory Plant precision scale, 0.001 kg precision

BOT-IOT-L01 TESTBED (development node in computer lab — enabled=1, ports/baud confirmed live by Pi):
  - dev_l01_ntc_nano_01  — Ford NTC temperature sensor, /dev/raven-port-C → ttyUSB2
  - dev_l01_ntc_nano_02  — Ford NTC temperature sensor, /dev/raven-port-B → ttyUSB1
  - dev_l01_soil         — Soil moisture sensor, /dev/raven-port-A → ttyUSB0
                           (enabled=1 only AFTER watchdog deployment verifies recovery)

Naming conventions:
  - scale_<plant>  → production scales (Juice, Dry, Mix, Formulated plant-floor; Lab precision)
  - dev_l01_<id>   → bot-iot-l01 development testbed sensors (clearly non-production)
  - Future bots:  dev_l02_<id>, dev_l03_<id>, etc.

Auto-run via bench migrate (registered in raven_ai_agent/patches.txt).

Manual run (if needed):
  bench --site erp.sysmayal2.cloud execute \\
    raven_ai_agent.patches.v0_3.create_sensor_skills_bot_iot_l01_and_fleet.execute

After the patch runs, the Pi reads each skill via:
  amb_w_spc.api.sensor_skill.get_sensor_skill_config(skill_id="<id>")

(Whitelisted, read-only — iot-bot@amb-wellness.com has access without role escalation.)

References:
  - JSON contract source: scripts/sensor_reader_dual.py on branch
    feat/l01-deployed-serial-sensor-reader-watchdog (raven_ai_agent, off V14.2.0)
    PR/compare: https://github.com/rogerboy38/raven_ai_agent/compare/V14.2.0...feat/l01-deployed-serial-sensor-reader-watchdog
  - Canonical Sensor Skill API: amb_w_spc.api.sensor_skill.get_sensor_skill_config
  - Legacy v15 seed (not run on PROD): amb_w_spc.patches.v15.04_create_sensor_skills_idempotent
  - udev rules: services/99-raven-sensors.rules (raven_ai_agent)
"""
import frappe
from frappe import _


# ─────────────────────────────────────────────────── PRODUCTION SCALE FLEET (5 placeholders)
PRODUCTION_SCALES = [
    {
        "name": "scale_juice",
        "skill_id": "scale_juice",
        "skill_name": "Juice Plant Endpoint Scale",
        "sensor_type": "Scale",
        "version": "0.1.0",
        "min_value": 0,
        "max_value": 500,   # plant-floor barrel scale, large capacity
        "unit_of_measure": "kg",
        "port": "/dev/ttyUSB0",   # placeholder — set per actual deployment
        "baud_rate": 9600,        # placeholder
        "python_config": '{"driver":"ModbusRTU","slave_id":1,"scale_factor":0.01,"precision_kg":0.010,"plant":"juice","note":"placeholder — tune when scale hardware selected"}',
        "wiring_instructions": "TODO: Confirm wiring once Juice plant scale hardware is selected (likely RS485-to-USB via ModbusRTU, similar to scale_plant pattern).",
        "calibration_procedure": "TODO: 0.010 kg precision class. Standard calibration procedure: zero → certified weight at 50% range → verify at 25% and 75%. Document scale_factor adjustment.",
        "enabled": 0,   # NOT DEPLOYED YET
    },
    {
        "name": "scale_dry",
        "skill_id": "scale_dry",
        "skill_name": "Dry Plant Endpoint Scale",
        "sensor_type": "Scale",
        "version": "0.1.0",
        "min_value": 0,
        "max_value": 500,
        "unit_of_measure": "kg",
        "port": "/dev/ttyUSB0",
        "baud_rate": 9600,
        "python_config": '{"driver":"ModbusRTU","slave_id":1,"scale_factor":0.01,"precision_kg":0.010,"plant":"dry","note":"placeholder — tune when scale hardware selected"}',
        "wiring_instructions": "TODO: Confirm wiring once Dry plant scale hardware is selected.",
        "calibration_procedure": "TODO: 0.010 kg precision class. Standard calibration procedure as above.",
        "enabled": 0,
    },
    {
        "name": "scale_mix",
        "skill_id": "scale_mix",
        "skill_name": "Mix Plant Endpoint Scale",
        "sensor_type": "Scale",
        "version": "0.1.0",
        "min_value": 0,
        "max_value": 500,
        "unit_of_measure": "kg",
        "port": "/dev/ttyUSB0",
        "baud_rate": 9600,
        "python_config": '{"driver":"ModbusRTU","slave_id":1,"scale_factor":0.01,"precision_kg":0.010,"plant":"mix","note":"placeholder — tune when scale hardware selected"}',
        "wiring_instructions": "TODO: Confirm wiring once Mix plant scale hardware is selected.",
        "calibration_procedure": "TODO: 0.010 kg precision class. Standard calibration procedure as above.",
        "enabled": 0,
    },
    {
        "name": "scale_formulated",
        "skill_id": "scale_formulated",
        "skill_name": "Formulated Plant Endpoint Scale",
        "sensor_type": "Scale",
        "version": "0.1.0",
        "min_value": 0,
        "max_value": 500,
        "unit_of_measure": "kg",
        "port": "/dev/ttyUSB0",
        "baud_rate": 9600,
        "python_config": '{"driver":"ModbusRTU","slave_id":1,"scale_factor":0.01,"precision_kg":0.010,"plant":"formulated","note":"placeholder — tune when scale hardware selected"}',
        "wiring_instructions": "TODO: Confirm wiring once Formulated plant scale hardware is selected.",
        "calibration_procedure": "TODO: 0.010 kg precision class. Standard calibration procedure as above.",
        "enabled": 0,
    },
    {
        "name": "scale_lab",
        "skill_id": "scale_lab",
        "skill_name": "Laboratory Precision Scale",
        "sensor_type": "Scale",
        "version": "0.2.0",     # bumped: this replaces the legacy v1.0.0 in the v15 seed
        "min_value": 0,
        "max_value": 30,        # 30 kg max for Laboratory Plant precision scale
        "unit_of_measure": "kg",
        "port": "/dev/ttyUSB1",
        "baud_rate": 115200,
        "python_config": '{"driver":"SerialCommand","command":"W","response_format":"DECIMAL","timeout":5,"precision_kg":0.001,"plant":"laboratory","note":"placeholder — confirm port/baud against deployed lab scale"}',
        "wiring_instructions": "USB-Serial to precision balance. Connect TX to RX, RX to TX. Verify COM port in Device Manager. (Legacy v1.0.0 wiring from v15 seed retained.)",
        "calibration_procedure": "0.001 kg precision class. 1. Warm up balance for 30 minutes. 2. Zero the balance. 3. Place 20kg certified weight. 4. Use calibration function per manufacturer instructions. 5. Verify with 10kg and 1kg test weights.",
        "enabled": 0,   # NOT DEPLOYED YET — flip to 1 when Lab scale is physically connected
    },
]


# ─────────────────────────────────────────────────── BOT-IOT-L01 TESTBED (3 dev sensors)
# Ports confirmed live by bot-iot-l01 Claude on 2026-06-16 21:03 CST:
#   /dev/raven-port-A → ttyUSB0 (phys 1-1.3)    — SOIL
#   /dev/raven-port-B → ttyUSB1 (phys 1-1.5.1)  — Ford NTC NANO-02
#   /dev/raven-port-C → ttyUSB2 (phys 1-1.5.2)  — Ford NTC NANO-01
#
# python_config values are PLACEHOLDERS until the Pi commits sensor_reader_dual.py to GitHub
# (which will reveal the actual JSON contract emitted by each Arduino).
DEV_TESTBED = [
    {
        "name": "dev_l01_ntc_nano_01",
        "skill_id": "dev_l01_ntc_nano_01",
        "skill_name": "bot-iot-l01 Testbed — Ford NTC NANO-01 Temperature",
        "sensor_type": "Temperature",   # DocType Select value (limited to Scale|Temperature|Pressure|Humidity|Flow|Counter|Generic)
        "version": "0.1.0",
        "min_value": -40,    # NTC thermistor typical range
        "max_value": 125,
        "unit_of_measure": "°C",
        "port": "/dev/raven-port-C",   # stable udev symlink → ttyUSB2 (phys 1-1.5.2)
        "baud_rate": 9600,   # CH340 default for Arduino Nano
        # JSON contract confirmed by sensor_reader_dual.py (Pi commit 2026-06-16):
        #   Emitted: {"id":"NANO-01","s":"NTC","raw":<int>,"mv":<float>,"n":<int>}
        #   Stored in IoT Sensor Reading with sensor_type="Ford Temperature", column=temperature
        "python_config": '{"driver":"ArduinoSerial","format":"JSON","reader":"sensor_reader_dual.py","emitted_keys":["id","s","raw","mv","n"],"sensor_id":"NANO-01","sensor_class":"NTC","iot_reading_sensor_type":"Ford Temperature","iot_reading_column":"temperature","watchdog":{"stall_timeout_s":90,"backoff_schedule_s":[5,10,20,40,80,160,300],"healthy_reset_s":120}}',
        "wiring_instructions": "Arduino Nano (CH340 1a86:7523) behind external USB hub at phys 1-1.5.2. NTC thermistor connected to Nano's analog input. Stable symlink via udev rule (services/99-raven-sensors.rules).",
        "calibration_procedure": "1. Compare reading against reference thermometer at room temperature (~22°C). 2. Adjust resistance lookup table or Steinhart-Hart coefficients in Nano firmware. 3. Verify at ice point (~0°C) and elevated temperature (~60°C).",
        "enabled": 1,   # actively emitting per Pi's 21:03 check (8 messages in last 25s)
    },
    {
        "name": "dev_l01_ntc_nano_02",
        "skill_id": "dev_l01_ntc_nano_02",
        "skill_name": "bot-iot-l01 Testbed — Ford NTC NANO-02 Temperature",
        "sensor_type": "Temperature",
        "version": "0.1.0",
        "min_value": -40,
        "max_value": 125,
        "unit_of_measure": "°C",
        "port": "/dev/raven-port-B",   # stable udev symlink → ttyUSB1 (phys 1-1.5.1)
        "baud_rate": 9600,
        "python_config": '{"driver":"ArduinoSerial","format":"JSON","reader":"sensor_reader_dual.py","emitted_keys":["id","s","raw","mv","n"],"sensor_id":"NANO-02","sensor_class":"NTC","iot_reading_sensor_type":"Ford Temperature","iot_reading_column":"temperature","watchdog":{"stall_timeout_s":90,"backoff_schedule_s":[5,10,20,40,80,160,300],"healthy_reset_s":120}}',
        "wiring_instructions": "Arduino Nano (CH340 1a86:7523) behind external USB hub at phys 1-1.5.1. NTC thermistor connected to Nano's analog input. Stable symlink via udev rule (services/99-raven-sensors.rules).",
        "calibration_procedure": "Same as dev_l01_ntc_nano_01. Calibrate both Nanos against the same reference for cross-validation.",
        "enabled": 1,   # actively emitting per Pi's 21:03 check (8 messages in last 25s)
    },
    {
        "name": "dev_l01_soil",
        "skill_id": "dev_l01_soil",
        "skill_name": "bot-iot-l01 Testbed — Soil Moisture",
        "sensor_type": "Humidity",   # closest fit in DocType's Select (Scale|Temperature|Pressure|Humidity|Flow|Counter|Generic)
        "version": "0.1.0",
        "min_value": 0,
        "max_value": 1024,    # raw ADC reading from capacitive soil sensor
        "unit_of_measure": "raw_adc",
        "port": "/dev/raven-port-A",   # stable udev symlink → ttyUSB0 (phys 1-1.3)
        "baud_rate": 9600,
        # JSON contract confirmed by sensor_reader_dual.py (Pi commit 2026-06-16):
        #   Emitted: {"id":"SOIL","s":"SOIL?","sm":<int>,"sd":<int>}
        #   Stored in IoT Sensor Reading with sensor_type="Soil Moisture", columns=soil_moisture, soil_dry
        "python_config": '{"driver":"ArduinoSerial","format":"JSON","reader":"sensor_reader_dual.py","emitted_keys":["id","s","sm","sd"],"sensor_id":"SOIL","sensor_class":"SoilMoisture","iot_reading_sensor_type":"Soil Moisture","iot_reading_columns":["soil_moisture","soil_dry"],"calibration_status":"FAULTY_HARDWARE","raw_dry_baseline":215,"raw_in_water":210,"watchdog":{"stall_timeout_s":90,"backoff_schedule_s":[5,10,20,40,80,160,300],"healthy_reset_s":120},"note":"raw_dry≈raw_in_water → sensor physical issue confirmed by Pi 2026-06-16; replace hardware before enable=1"}',
        "wiring_instructions": "Capacitive soil moisture sensor on RPi onboard USB at phys 1-1.3. Stable symlink via udev rule. Currently subject to flake — 90s watchdog deployed 2026-06-16 (sensor_reader_dual.py, branch feat/l01-deployed-serial-sensor-reader-watchdog) auto-reconnects on stall.",
        "calibration_procedure": "Calibration unreliable as of 2026-06-16 — sensor in water reads sm=209-230, dry baseline ~210-223, sd=0 throughout. Physical hardware issue confirmed. Replace sensor and re-characterize before relying on readings. Note: watchdog keeps the port healthy regardless, so flake recovery is automatic — but no useful data until hardware swap.",
        "enabled": 0,   # KEEP DISABLED until watchdog verifies stable recovery AND hardware swap addressed
    },
]


def execute():
    """Idempotent seed for production scale fleet + bot-iot-l01 testbed."""
    print("=" * 70)
    print("raven_ai_agent v0.3 — Sensor Skill seed (fleet + testbed)")
    print("=" * 70)

    if not frappe.db.exists("DocType", "Sensor Skill"):
        print("ERROR: Sensor Skill DocType not found. Ensure amb_w_spc is installed.")
        return

    all_skills = PRODUCTION_SCALES + DEV_TESTBED

    created = 0
    updated = 0
    unchanged = 0

    for data in all_skills:
        name = data["name"]
        if frappe.db.exists("Sensor Skill", name):
            doc = frappe.get_doc("Sensor Skill", name)
            changed = False
            for k, v in data.items():
                if k == "name":
                    continue
                if doc.get(k) != v:
                    doc.set(k, v)
                    changed = True
            if changed:
                doc.save(ignore_permissions=True)
                frappe.db.commit()
                updated += 1
                print(f"  UPDATED:   {name}")
            else:
                unchanged += 1
                print(f"  UNCHANGED: {name}")
        else:
            try:
                doc = frappe.get_doc({"doctype": "Sensor Skill", **data})
                doc.insert(ignore_permissions=True)
                frappe.db.commit()
                created += 1
                enabled_str = "[LIVE]" if data["enabled"] else "[placeholder]"
                print(f"  CREATED:   {name} {enabled_str}")
            except Exception as e:
                print(f"  ERROR:     {name}: {e}")

    print("-" * 70)
    print(f"Summary: Created={created}  Updated={updated}  Unchanged={unchanged}")
    print("-" * 70)

    # Verification: list all enabled vs disabled
    print("\nFinal state on PROD:")
    all_rows = frappe.get_all(
        "Sensor Skill",
        fields=["name", "skill_name", "sensor_type", "port", "enabled"],
        order_by="enabled desc, name",
    )
    for r in all_rows:
        status = "LIVE" if r.enabled else "placeholder"
        print(f"  [{status:11s}] {r.name:30s} {r.sensor_type:12s} {r.port}")

    print("\nDone. Pi can now query via:")
    print('  amb_w_spc.api.sensor_skill.get_sensor_skill_config(skill_id="<id>")')


if __name__ == "__main__":
    execute()
