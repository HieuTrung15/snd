// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Báo cáo danh sách nhân viên nghỉ việc"] = {
	"filters": [
		{
            "fieldname": "from_date",
            "label": __("Ngày nghỉ từ"),
            "fieldtype": "Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1)
        },
        {
            "fieldname": "to_date",
            "label": __("Ngày nghỉ đến"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today()
        },
        {
            "fieldname": "department",
            "label": __("Phòng ban"),
            "fieldtype": "Link",
            "options": "Department"
        },
        {
            "fieldname": "employee",
            "label": __("Nhân viên"),
            "fieldtype": "Link",
            "options": "Employee"
        },
		{
			"fieldname": "company",
			"label": __("Công ty"),
			"fieldtype": "Link",
			"options": "Company",
			"reqd": 1,
			"default": frappe.defaults.get_user_default("Company")
		}
	]
};
