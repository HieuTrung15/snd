// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Danh sách sinh nhật"] = {
	"filters": [
        {
            "fieldname": "month",
            "label": __("Chọn tháng"),
            "fieldtype": "Select",
            "options": "\n1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12",
            "default": frappe.datetime.get_today().split('-')[1]
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
