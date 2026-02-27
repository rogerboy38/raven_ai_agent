frappe.query_reports["IoT Sensor Dashboard"] = {
    filters: [
        {
            fieldname: "device_name",
            label: __("Device"),
            fieldtype: "Data",
        },
        {
            fieldname: "sensor_type",
            label: __("Sensor Type"),
            fieldtype: "Select",
            options: "\nDHT11\nDHT22\nBMP280\nBME280\nDS18B20\nMQ-2\nPIR\nUltrasonic\nLight\nSoil Moisture\nOther",
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
        },
    ],
};
