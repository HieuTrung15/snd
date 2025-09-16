// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["BÁO CÁO TÌNH HÌNH SỬ DỤNG LAO ĐỘNG"] = {
	"filters": [
		{
            "fieldname": "company",
            "label": "Công ty",
            "fieldtype": "Link",
            "options": "Company",
            "reqd": 1
        },
        {
            "fieldname": "from_date",
            "label": "Từ ngày",
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.datetime.month_start()
        },
        {
            "fieldname": "to_date",
            "label": "Đến ngày",
            "fieldtype": "Date",
            "reqd": 1,
            "default": frappe.datetime.month_end()
        }
	]
};
