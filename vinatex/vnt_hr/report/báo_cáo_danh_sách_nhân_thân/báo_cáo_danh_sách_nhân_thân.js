// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Báo cáo danh sách nhân thân"] = {
	 "filters": [
        {
            "fieldname": "employee",
            "label": __("Nhân viên"),
            "fieldtype": "Link",
            "options": "Employee"
        },
        {
            "fieldname": "department",
            "label": __("Phòng ban"),
            "fieldtype": "Link",
            "options": "Department"
        }
    ]
};
