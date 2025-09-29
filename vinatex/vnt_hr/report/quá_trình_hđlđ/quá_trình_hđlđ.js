// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Quá trình HĐLĐ"] = {
	"filters": [
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
