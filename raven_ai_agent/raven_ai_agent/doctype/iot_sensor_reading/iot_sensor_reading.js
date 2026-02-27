// Copyright (c) 2026, Raven AI Agent and contributors
// For license information, please see license.txt

frappe.ui.form.on('IoT Sensor Reading', {
    refresh: function(frm) {
        if (frm.doc.status === 'Error') {
            frm.dashboard.set_headline_alert(
                '<div class="alert alert-danger">Sensor reporting errors</div>'
            );
        }
        if (frm.doc.battery_level && frm.doc.battery_level < 20) {
            frm.dashboard.set_headline_alert(
                '<div class="alert alert-warning">Low battery: ' + frm.doc.battery_level + '%</div>'
            );
        }
    }
});
