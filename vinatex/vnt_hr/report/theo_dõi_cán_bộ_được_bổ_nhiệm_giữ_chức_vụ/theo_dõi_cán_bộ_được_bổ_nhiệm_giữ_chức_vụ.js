// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["THEO DÕI CÁN BỘ ĐƯỢC BỔ NHIỆM GIỮ CHỨC VỤ"] = {
	"filters": [
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
