// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Số lượng nhân viên theo phòng ban"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 0,
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Active", "On Leave", "Suspended", "Left"].join("\n"),
			default: "Active",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
	],

	// Nếu muốn dựng chart phía client thay vì server, có thể dùng get_chart_data.
	// Ở đây server đã trả chart rồi, nhưng vẫn để dự phòng khi cần custom.
	get_chart_data(columns, data) {
		const top10 = data.slice(0, 10);
		const labels = top10.map(r => r.short_name);
		const values = top10.map(r => r.total);
		return {
			data: { labels, datasets: [{ name: __("Employees"), values }] },
			type: "bar",
			height: 300,
		};
	},

  // Tùy chọn: tinh chỉnh hiển thị bảng
    formatter: function (value, row, column, data, default_formatter) {
		// Bôi đậm cột phòng ban
		if (column.fieldname === "department") {
			value = `<b>${frappe.utils.escape_html(value || "")}</b>`;
			return value;
		}
		return default_formatter(value, row, column, data);
	},
};