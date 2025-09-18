// Copyright (c) 2025, vinatex
// For license information, please see license.txt

frappe.query_reports["Báo cáo nhân viên theo chức danh"] = {
	"filters": [
		{
			"fieldname": "designation",
			"label": __("Chức danh"),
			"fieldtype": "Link",
			"options": "Designation",
			"reqd": 0
		},
		{
			"fieldname": "company",
			"label": __("Công ty"),
			"fieldtype": "Link",
			"options": "Company",
			"reqd": 0
		}
	],

	onload: function(report) {
		// Khi report load xong -> override chart
		report.page.add_inner_button(__("Xem Biểu đồ"), function() {
			console.log("Vẽ chart");
			let labels_full = report.data.map(d => d.designation_full); // full name
			let abbrs = report.data.map(d => d.designation); // abbr
			let counts = report.data.map(d => d.employee_count);

			let chart = new frappe.Chart(report.page.wrapper.find(".layout-main-section").get(0), {
				data: {
					labels: labels_full,  // để tooltip luôn hiển thị full
					datasets: [
						{
							name: "Số lượng nhân viên",
							values: counts
						}
					]
				},
				type: 'bar',
				height: 300
			});

			// ép lại trục X hiển thị abbr
			chart.chart.update({
				labels: abbrs
			});
		});
	}
};
