// Copyright (c) 2026, Vinatex and contributors
// License: MIT. See LICENSE

frappe.query_reports["VNT Daily Attendance"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("Từ ngày"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("Đến ngày"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{ fieldname: "company", label: __("Công ty"), fieldtype: "Link", options: "Company" },
		{
			fieldname: "department",
			label: __("Phòng ban"),
			fieldtype: "Link",
			options: "Department",
		},
		{ fieldname: "employee", label: __("Nhân viên"), fieldtype: "Link", options: "Employee" },
		{
			fieldname: "shift_group",
			label: __("Kíp"),
			fieldtype: "Link",
			options: "VNT Shift Group",
		},
		{
			fieldname: "shift_type",
			label: __("Loại ca"),
			fieldtype: "Link",
			options: "Shift Type",
		},
		{
			fieldname: "attendance_status",
			label: __("Trạng thái chấm công"),
			fieldtype: "Select",
			context: "VNT Daily Attendance",
			options:
				"\nPresent\nAbsent\nOn Leave\nHalf Day\nWork From Home\nWork Trip\nDraft Attendance\nNot Created\nNot Required (Shift OFF)",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "attendance_status" && value)
			value = __(value, null, "VNT Daily Attendance");
		return default_formatter(value, row, column, data);
	},
};
