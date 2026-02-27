# Copyright (c) 2026, Raven AI Agent and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class IoTSensorReading(Document):
    def before_insert(self):
        if not self.reading_timestamp:
            self.reading_timestamp = now_datetime()

    def validate(self):
        self.validate_sensor_ranges()

    def validate_sensor_ranges(self):
        if self.temperature is not None and (self.temperature < -50 or self.temperature > 80):
            frappe.msgprint("Temperature reading seems out of normal range (-50 to 80 C)", indicator="orange", alert=True)
        if self.humidity is not None and (self.humidity < 0 or self.humidity > 100):
            frappe.throw("Humidity must be between 0 and 100%")
        if self.battery_level is not None and (self.battery_level < 0 or self.battery_level > 100):
            frappe.throw("Battery level must be between 0 and 100%")
