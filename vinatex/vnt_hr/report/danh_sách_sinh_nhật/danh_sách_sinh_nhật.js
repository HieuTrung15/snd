// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Danh sách sinh nhật"] = {
	"filters": [
        {
            "fieldname": "from_date",
            "label": __("Từ ngày"),
            "fieldtype": "Date",
            "default": frappe.datetime.month_start()
        },
        {
            "fieldname": "to_date",
            "label": __("Đến ngày"),
            "fieldtype": "Date",
            "default": frappe.datetime.month_end()
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
        }
    ]
};
