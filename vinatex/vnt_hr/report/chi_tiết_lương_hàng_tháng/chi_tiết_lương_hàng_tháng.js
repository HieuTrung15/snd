// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

const vntMonthlySalaryDefaultEmployee = (frappe.boot && frappe.boot.employee) || null;

frappe.query_reports["Chi tiết lương hàng tháng"] = {
	filters: [
		{
			fieldname: "year",
			label: __("Năm"),
			fieldtype: "Int",
			default: new Date().getFullYear(),
			reqd: 1,
		},
		{
			fieldname: "employee",
			label: __("Nhân sự"),
			fieldtype: "Link",
			options: "Employee",
			default: vntMonthlySalaryDefaultEmployee,
			hidden: 1,
			read_only: 1,
			get_query: () => ({
				filters: {
					status: "Active",
				},
			}),
		},
	],
};
