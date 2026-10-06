// Copyright (c) 2026, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Thống kê lao động theo vị trí công việc"] = {
	"filters": [
		{
			"fieldname": "status",
			"label": __("Trạng thái"),
			"fieldtype": "Select",
			"options": ["Tất cả", "Active", "Inactive", "Suspended", "Left"].join("\n"),
			"default": "Active"
		},
		{
			"fieldname": "branch",
			"label": __("Chi nhánh"),
			"fieldtype": "Link",
			"options": "Branch"
		},
		{
			"fieldname": "department",
			"label": __("Phòng ban"),
			"fieldtype": "Link",
			"options": "Department",
			"get_query": function () {
				return { filters: { is_group: 0 } };
			}
		},
		{
			"fieldname": "designation",
			"label": __("Vị trí công việc"),
			"fieldtype": "Link",
			"options": "Designation"
		},
		{
			"fieldname": "designation_group",
			"label": __("Nhóm chức vụ"),
			"fieldtype": "Link",
			"options": "VNT Designation Group"
		},
		{
			"fieldname": "search_text",
			"label": __("Tìm nhanh"),
			"fieldtype": "Data"
		}
	]
};
