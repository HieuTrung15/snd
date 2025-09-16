// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["BÁO CÁO BIẾN ĐỘNG TĂNG GIẢM LĐ"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": "Từ ngày",
			"fieldtype": "Date",
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": "Đến ngày",
			"fieldtype": "Date",
			"reqd": 1
		}
	]
};
