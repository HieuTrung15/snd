// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Số nhân viên đi công tác"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": "From",
			"fieldtype": "Date",
			"default": frappe.datetime.week_start()
		},
		{
			"fieldname": "to_date",
			"label": "To",
			"fieldtype": "Date",
			"default": frappe.datetime.week_end()
		},
		{
			"fieldname": "department",
			"label": "Department",
			"fieldtype": "Link",
			"options": "Department",
			"default": ""   
		}
	]
};
