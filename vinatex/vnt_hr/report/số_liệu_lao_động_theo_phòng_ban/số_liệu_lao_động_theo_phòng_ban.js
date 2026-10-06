// Copyright (c) 2026, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Số liệu lao động theo phòng ban"] = {
	"filters": [
		{
			fieldname: "company",
			label: __("Công ty"),
			fieldtype: "Link",
			options: "Company"
		},
		{
			fieldname: "status",
			label: __("Trạng thái"),
			fieldtype: "Select",
			options: ["Tất cả", "Active", "Inactive", "Suspended", "Left"].join("\n"),
			default: "Active"
		},
		{
			fieldname: "department",
			label: __("Phòng ban"),
			fieldtype: "Link",
			options: "Department",
			get_query: function () {
				const company = frappe.query_report.get_filter_value("company");
				return {
					filters: {
						...(company ? { company } : {}),
						is_group: 0,
						disabled: 0
					}
				};
			}
		},
		{
			fieldname: "branch",
			label: __("Chi nhánh"),
			fieldtype: "Link",
			options: "Branch"
		}
	],

	formatter: function (value, row, column, data, default_formatter) {
		// Bôi đậm tên phòng ban
		if (column.fieldname === "department_name") {
			return `<b>${frappe.utils.escape_html(value || "")}</b>`;
		}
		return default_formatter(value, row, column, data);
	}
};
