// Copyright (c) 2026, Vinatex and contributors
// License: MIT. See LICENSE

frappe.ui.form.on("VNT Shift Group", {
	refresh(frm) {
		if (
			frm.is_new() ||
			!(frappe.user.has_role("HR Manager") || frappe.user.has_role("System Manager"))
		)
			return;

		frm.add_custom_button(
			__("Xem trước ca kế hoạch"),
			() => {
				open_generation_dialog(frm, true);
			},
			__("Quản lý ca/kíp"),
		);

		frm.add_custom_button(
			__("Tạo ca kế hoạch"),
			() => {
				open_generation_dialog(frm, false);
			},
			__("Quản lý ca/kíp"),
		);

		frm.add_custom_button(
			__("Đồng bộ danh sách ngày nghỉ"),
			() => {
				const dialog = new frappe.ui.Dialog({
					title: __("Đồng bộ danh sách ngày nghỉ"),
					fields: [
						{
							fieldname: "year",
							fieldtype: "Int",
							label: __("Năm"),
							default: frappe.datetime.get_today().slice(0, 4),
							reqd: 1,
						},
					],
					primary_action_label: __("Kiểm tra và đồng bộ"),
					primary_action(values) {
						frappe.confirm(
							__(
								"Chỉ tạo danh sách ngày nghỉ hằng tuần mới khi không có xung đột? Danh sách hiện có sẽ không bị thay đổi.",
							),
							() => {
								dialog.hide();
								frappe.call({
									method: "vinatex.vnt_hr.shift_management.holiday_service.sync_shift_group_holiday_list",
									args: { shift_group: frm.doc.name, year: values.year },
									freeze: true,
									callback: (r) => {
										frappe.msgprint({
											title: __("Danh sách ngày nghỉ"),
											message: `<pre>${frappe.utils.escape_html(JSON.stringify(r.message, null, 2))}</pre>`,
										});
										frm.reload_doc();
									},
								});
							},
						);
					},
				});
				dialog.show();
			},
			__("Quản lý ca/kíp"),
		);
	},
});

function open_generation_dialog(frm, preview_only) {
	const dialog = new frappe.ui.Dialog({
		title: preview_only ? __("Xem trước ca kế hoạch") : __("Tạo ca kế hoạch"),
		fields: [
			{
				fieldname: "from_date",
				fieldtype: "Date",
				label: __("Từ ngày"),
				default: frappe.datetime.get_today(),
				reqd: 1,
			},
			{ fieldname: "to_date", fieldtype: "Date", label: __("Đến ngày"), reqd: 1 },
			{
				fieldname: "employee",
				fieldtype: "Link",
				label: __("Nhân viên"),
				options: "Employee",
			},
		],
		primary_action_label: preview_only ? __("Xem trước") : __("Tạo ca"),
		primary_action(values) {
			const run = () => {
				dialog.hide();
				frappe.call({
					method: preview_only
						? "vinatex.vnt_hr.shift_management.shift_assignment_service.preview_shift_assignments_api"
						: "vinatex.vnt_hr.shift_management.shift_assignment_service.generate_shift_assignments_api",
					args: { ...values, shift_group: frm.doc.name },
					freeze: true,
					callback: (r) => show_generation_result(r.message),
				});
			};

			if (preview_only) run();
			else
				frappe.confirm(
					__(
						"Chỉ tạo ca còn thiếu và giữ nguyên mọi ca hiện có/ca thủ công?",
					),
					run,
				);
		},
	});
	dialog.show();
}

function show_generation_result(result) {
	frappe.msgprint({
		title: __("Kết quả tạo ca kế hoạch"),
		message: `<pre style="max-height: 500px; overflow: auto">${frappe.utils.escape_html(JSON.stringify(result, null, 2))}</pre>`,
		wide: true,
	});
}
