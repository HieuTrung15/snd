// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["DANH SÁCH CÁN BỘ ĐÃ NGHỈ HƯU"] = {
	"filters": [
		{
            "fieldname": "company",
            "label": __("Công ty"),
            "fieldtype": "Link",
            "options": "Company",
            "reqd": 0
        },
        {
            "fieldname": "department",
            "label": __("Phòng ban"),
            "fieldtype": "Link",
            "options": "Department",
            "reqd": 0
        },
        {
            "fieldname": "retirement_from",
            "label": __("Từ ngày"),
            "fieldtype": "Date",
            "reqd": 0
        },
        {
            "fieldname": "retirement_to",
            "label": __("Đến ngày"),
            "fieldtype": "Date",
            "reqd": 0
        },
        {
            "fieldname": "employee_name",
            "label": __("Tên nhân viên"),
            "fieldtype": "Data",
            "reqd": 0
        }
	]
};
