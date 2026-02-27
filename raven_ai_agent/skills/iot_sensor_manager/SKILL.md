---
name: iot_sensor_manager
description: Manages IoT sensor readings, alerts, and status for RPi bots L01-L30
version: 1.0.0
author: Raven AI Agent
triggers:
  - sensor
  - temperature
  - humidity
  - motion
  - light
  - sensor reading
  - sensor status
  - iot
  - rpi
  - bot status
  - temperatura
  - humedad
  - movimiento
metadata:
  raven:
    emoji: "📡"
    category: iot
    priority: 70
  sensors:
    - type: temperature
      model: DHT22
      gpio: 4
    - type: humidity
      model: DHT22
      gpio: 4
    - type: motion
      model: HC-SR501
      gpio: 17
    - type: light
      model: BH1750
      gpio: 27
---

# IoT Sensor Manager Skill

Unified skill for managing all IoT sensor operations on RPi bots (L01-L30).

## Features

- Read individual sensor values (temperature, humidity, motion, light)
- Full bot sensor status overview
- Threshold-based alert system with critical/warning levels
- Historical reading queries
- Bilingual support (English/Spanish)
- Logs readings to ERPNext IoT Sensor Reading DocType

## Supported Sensors

| Sensor | Model | GPIO | Unit |
|--------|-------|------|------|
| Temperature | DHT22 | 4 | C |
| Humidity | DHT22 | 4 | % |
| Motion | HC-SR501 | 17 | boolean |
| Light | BH1750 | 27 | lux |

## Usage Examples

- "Check temperature on L01"
- "Sensor status L05"
- "Show humidity history for L12"
- "Sensor alerts L01"
- "Temperatura del bot L03"
