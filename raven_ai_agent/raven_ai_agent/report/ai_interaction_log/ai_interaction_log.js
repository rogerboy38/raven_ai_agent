// Copyright (c) 2025, Raven AI Agent and contributors
// For license information, please see license.txt

frappe.query_reports["AI Interaction Log"] = {
	filters: [
		{
			fieldname: "user",
			label: __("User"),
			fieldtype: "Link",
			options: "User",
			width: 180,
		},
		{
			fieldname: "memory_type",
			label: __("Memory Type"),
			fieldtype: "Select",
			options: "\nFact\nPreference\nSummary\nCorrection",
			width: 120,
		},
		{
			fieldname: "importance",
			label: __("Importance"),
			fieldtype: "Select",
			options: "\nCritical\nHigh\nNormal\nLow",
			width: 100,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			width: 120,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			width: 120,
		},
		{
			fieldname: "verified_only",
			label: __("Verified Only"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
