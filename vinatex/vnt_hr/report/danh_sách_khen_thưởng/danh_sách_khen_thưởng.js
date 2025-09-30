// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Danh sách khen thưởng"] = {
	"filters": [
		{
            "fieldname":"employee",
            "label": __("Nhân sự"),
            "fieldtype": "Link",
            "options": "Employee"
        },
		{
            "fieldname":"department",
            "label": __("Phòng/Ban"),
            "fieldtype": "Link",
            "options": "Department"        
        }
	]
};
