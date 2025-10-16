// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.query_reports["Số nhân sự đi làm hôm nay"] = {
	filters: [
		{
			fieldname: "employee",
			label: __("Mã/Tên nhân sự"),
			fieldtype: "Link",
			options: "Employee",
			reqd: 0,
		},
		{
			fieldname: "department",
			label: __("Phòng ban"),
			fieldtype: "Link",
			options: "Department",
			reqd: 0,
		},
		{
			fieldname: "branch",
			label: __("Chi nhánh"),
			fieldtype: "Link",
			options: "Branch",
			reqd: 0,
		},
		{
			fieldname: "user",
			label: __("Người dùng"),
			fieldtype: "Link",
			options: "User",
			hidden: 1,
			default: frappe.session.user,
		},
	],
	onload(report) {
		const user = frappe.session.user;

		// Lấy Employee theo user hiện tại (ưu tiên đang Active)
		frappe.db
			.get_list("Employee", {
				fields: ["name", "branch"],
				filters: { user_id: user, status: "Active" },
				limit: 1,
			})
			.then((list) => {
				const emp = list && list[0];
				if (emp && emp.branch) {
					// set giá trị filter 'branch'
					report.set_filter_value("branch", emp.branch);

					// tuỳ chọn: đặt read-only để tránh bị sửa nhầm (bỏ nếu không muốn)
					const f = report.get_filter("branch");
					if (f && f.df) f.df.read_only = 1;

					// tuỳ chọn: lưu default để khi mở lại route vẫn có
					if (f && f.df) f.df.default = emp.branch;
				}
			})
			.catch(console.error);
	},
};


