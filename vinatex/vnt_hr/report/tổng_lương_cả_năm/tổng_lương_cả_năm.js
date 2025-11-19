// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

const vntAnnualSalaryDefaultEmployee =
	(frappe.boot && frappe.boot.employee) || null;
const vntAnnualSalaryDefaultMonth = String(new Date().getMonth() + 1).padStart(2, "0");
const vntAnnualSalaryMonthOptions = ["01","02","03","04","05","06","07","08","09","10","11","12"].join("\n");

frappe.query_reports["Tổng lương cả năm"] = {
	filters: [
		{
			fieldname: "year",
			label: __("Năm"),
			fieldtype: "Int",
			default: new Date().getFullYear(),
			reqd: 1,
		},
		{
			fieldname: "month",
			label: __("Tháng"),
			fieldtype: "Select",
			options: vntAnnualSalaryMonthOptions,
			default: vntAnnualSalaryDefaultMonth,
			reqd: 1,
		},
		{
			fieldname: "employee",
			label: __("Nhân sự"),
			fieldtype: "Link",
			options: "Employee",
			default: vntAnnualSalaryDefaultEmployee,
			hidden: 1,
			get_query: () => ({
				filters: {
					status: "Active",
				},
			}),
		},
	],
};
