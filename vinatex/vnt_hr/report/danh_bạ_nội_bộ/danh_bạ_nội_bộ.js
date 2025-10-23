// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Danh bạ nội bộ"] = {
	"filters": [
		{
            "fieldname":"employee",
            "label": __("Nhân sự"),
            "fieldtype": "Link",
            "options": "Employee",
            "ignore_permissions": 1,
            "ignore_user_permissions": 1
        },
		{
            "fieldname":"company",
            "label": __("Công ty"),
            "fieldtype": "Link",
            "options": "Company",
            "default": frappe.defaults.get_user_default("Company")
        },
		{
            "fieldname":"department",
            "label": __("Phòng/Ban"),
            "fieldtype": "Link",
            "options": "Department",
			"get_query": function() {
				const company = frappe.query_report.get_filter_value("company");
				return {
				filters: {
					...(company ? { company } : {}),
					is_group: 0
				}
				};
			}
        }
	]
};
