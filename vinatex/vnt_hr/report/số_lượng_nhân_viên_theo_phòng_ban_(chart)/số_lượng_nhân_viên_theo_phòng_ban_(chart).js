// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Số lượng nhân viên theo phòng ban (chart)"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 0,
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Active", "On Leave", "Suspended", "Left"].join("\n"),
			default: "Active",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
	],
};
