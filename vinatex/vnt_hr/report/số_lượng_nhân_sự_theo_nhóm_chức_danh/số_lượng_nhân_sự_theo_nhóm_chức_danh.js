// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Số lượng nhân sự theo nhóm chức danh"] = {
	"filters": [
		{
			"fieldname": "Công ty/Đơn vị",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company"
		}
	],

	get_chart_data: function (columns, result) {
		return result.chart;
	}
};
