// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["THEO DÕI CÁN BỘ ĐƯỢC BỔ NHIỆM GIỮ CHỨC VỤ"] = {
    "filters": [
        {
            "fieldname": "company",
            "label": "Công ty",
            "fieldtype": "Link",
            "options": "Company"
        },
        {
            "fieldname": "department",
            "label": "Phòng ban",
            "fieldtype": "Link",
            "options": "Department"
        },
        {
            "fieldname": "from_date",
            "label": "Ngày tạo QĐ từ ngày ",
            "fieldtype": "Date"
        },
        {
            "fieldname": "to_date",
            "label": "Đến ngày ",
            "fieldtype": "Date",
            "default": frappe.datetime.get_today()
        },
        {
            "fieldname": "only_latest_per_employee",
            "label": "Chỉ lấy quyết định mới nhất mỗi nhân viên",
            "fieldtype": "Check",
            "default": 1
        }
    ]
};
