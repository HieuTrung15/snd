// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Attendance Confirm", {
	onload(frm) {
		_update_parent_status(frm);
	},

	refresh(frm) {
		frm.set_df_property("items", "cannot_delete_rows", true);
		frm.set_df_property("items", "cannot_add_rows", true);
		_render_guidance(frm);
		_update_parent_status(frm);

		if (!frm.is_new()) {
			frm.add_custom_button(__("Cập nhật dữ liệu bất thường"), () => {
				frappe.call({
					method: "vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.refresh_attendance_confirm",
					args: { docname: frm.doc.name },
					freeze: true,
					freeze_message: __("Đang đối chiếu ca kế hoạch và dữ liệu chấm công..."),
					callback() {
						frappe.show_alert({
							message: __("Đã cập nhật dữ liệu bất thường."),
							indicator: "green",
						});
						frm.reload_doc();
					},
				});
			}, __("Thao tác"));
		}

		frm.add_custom_button(__("Áp dụng giải trình chung"), () => {
			const explanation = (frm.doc.bulk_explanation || "").trim();
			if (!explanation) {
				frappe.msgprint(__("Vui lòng nhập Giải trình chung trước."));
				return;
			}
			(frm.doc.items || []).forEach((row) => {
				if (!row.type) {
					frappe.model.set_value(row.doctype, row.name, "type", explanation);
				}
			});
			refresh_field("items");
			_update_parent_status(frm);
		}, __("Thao tác"));

		if ((frm.doc.items || []).some((row) => row.issue_code === "EARLY_EXIT")) {
			frm.add_custom_button(__("Xử lý các ngày Sm"), () => {
				const pending_rows = (frm.doc.items || []).filter(
					(row) => row.issue_code === "EARLY_EXIT" && !row.confirm
				);
				if (!pending_rows.length) {
					frappe.show_alert({
						message: __("Không còn ngày Sm nào đang chờ HR."),
						indicator: "blue",
					});
					return;
				}

				frappe.prompt([
					{
						fieldname: "explanation",
						fieldtype: "Small Text",
						label: __("Giải trình / Căn cứ"),
						reqd: 1,
					},
					{
						fieldname: "decision",
						fieldtype: "Select",
						label: __("Kết quả HR"),
						options: "Đồng ý\nTừ chối",
						reqd: 1,
						default: "Đồng ý",
					},
				], (values) => {
					pending_rows.forEach((row) => {
						row.type = values.explanation;
						row.confirm = values.decision;
						row.__unsaved = 1;
					});
					frm.dirty();
					refresh_field("items");
					_update_parent_status(frm);
					frm.save().then(() => {
						frappe.show_alert({
							message: __("Đã xử lý {0} ngày Sm.", [pending_rows.length]),
							indicator: "green",
						}, 6);
					});
				}, __("Xử lý các ngày về sớm"), __("Áp dụng"));
			}, __("Thao tác"));
		}
	},

	confirm(frm) {
		if (!frm.doc.confirm) return;
		let missing_explanation = 0;
		(frm.doc.items || []).forEach((row) => {
			if (!row.type) {
				missing_explanation += 1;
				return;
			}
			frappe.model.set_value(row.doctype, row.name, "confirm", frm.doc.confirm);
		});
		if (missing_explanation) {
			frappe.show_alert({
				message: __(
					"Có {0} dòng chưa có giải trình nên chưa được xác nhận.",
					[missing_explanation]
				),
				indicator: "orange",
			}, 6);
		}
		refresh_field("items");
		_update_parent_status(frm);
	},

	validate(frm) {
		_update_parent_status(frm);
	},
});


frappe.ui.form.on("VNT Attendance Confirm Item", {
	type(frm) {
		_update_parent_status(frm);
	},
	confirm(frm) {
		_update_parent_status(frm);
	},
});


function _update_parent_status(frm) {
	const items = frm.doc.items || [];
	let status = "Chờ giải trình";
	if (items.length && items.every((row) => Boolean(row.type))) {
		status = items.every((row) => Boolean(row.confirm))
			? "Đã xác nhận"
			: "Chờ xác nhận";
	}
	if (frm.doc.status !== status) {
		frm.doc.status = status;
		refresh_field("status");
	}
}


function _render_guidance(frm) {
	const field = frm.fields_dict.guidance_html;
	if (!field || !field.$wrapper) return;
	field.$wrapper.html(`
		<div class="alert alert-info mb-0">
			<div><strong>${__("Cách xử lý")}</strong></div>
			<div>${__("1. Mở từng dòng để xem ca kế hoạch, các lần chấm trong ca và ngoài ca.")}</div>
			<div>${__("2. Nhập Giải trình/Căn cứ, sau đó chọn Đồng ý hoặc Từ chối. Chỉ cần lưu một lần, không có cấp duyệt tiếp theo.")}</div>
			<div>${__("3. Dấu + là có từ hai lần chấm ngoài ca; +1 là chỉ có một lần chấm ngoài ca và chưa đủ để kết luận một ca làm việc.")}</div>
			<div>${__("4. Với Về sớm (Sm): Đồng ý sẽ chuyển kết quả bảng công thành X; Từ chối sẽ giữ Sm. Nếu vừa Tr/Sm thì Đồng ý chỉ bỏ Sm và vẫn giữ Tr.")}</div>
			<div class="mt-2 text-muted">${__("Phiếu này chỉ lưu kết quả kiểm tra của HR, không tự tạo hoặc sửa Checkin/Attendance.")}</div>
		</div>
	`);
}
