// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["BÁO CÁO CƠ CẤU LAO ĐỘNG THEO NHÓM TUỔI"] = {
	"filters": [
        {
            "fieldname": "to_date",
            "label": __("Tính đến ngày"),
            "fieldtype": "Date",
            "default": frappe.datetime.get_today(),
            "reqd": 1
        },
        {
            "fieldname": "department",
            "label": __("Phòng ban"),
            "fieldtype": "Link",
            "options": "Department",
            "reqd": 0
        },
        {
            "fieldname": "gender",
            "label": __("Giới tính"),
            "fieldtype": "Select",
            "options": "\nMale\nFemale",
            "reqd": 0
        }
	]
};
