// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Danh sách cán bộ lãnh đạo, quản lý"] = {
	"filters": [
		 {
            "fieldname": "company",
            "label": "Công ty",
            "fieldtype": "Link",
            "options": "Company",
            "reqd": 0
        },
        {
            "fieldname": "department",
            "label": "Phòng ban",
            "fieldtype": "Link",
            "options": "Department",
            "reqd": 0
        },
        {
            "fieldname": "status",
            "label": "Trạng thái",
            "fieldtype": "Select",
            "options": ["Tất cả", "Active", "On Leave", "Left"].join("\n"),
            "default": "Active"
        },
        {
            "fieldname": "group_mode",
            "label": "Nhóm chức danh",
            "fieldtype": "Select",
            "options": [
                "Cả hai: Người quản lý + Lãnh đạo cấp trung",
                "Người quản lý",
                "Lãnh đạo cấp trung"
            ].join("\n"),
            "default": "Cả hai: Người quản lý + Lãnh đạo cấp trung"
        },
        {
            "fieldname": "search_text",
            "label": "Tìm nhanh (Mã/Tên/Chức danh)",
            "fieldtype": "Data",
            "reqd": 0
        }
	]
};
