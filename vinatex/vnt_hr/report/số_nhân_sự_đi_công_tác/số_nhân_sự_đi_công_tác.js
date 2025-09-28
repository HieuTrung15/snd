// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Số nhân sự đi công tác"] = {
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
			"fieldname": "type_leave",
			"label": "Type",
			"fieldtype": "Data",
			"default": "Công tác"
		},
		{
			"fieldname": "department",
			"label": "Department",
			"fieldtype": "Link",
			"options": "Department"
		}
	]
};
