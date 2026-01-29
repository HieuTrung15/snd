// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt
// VGT00065
frappe.ui.form.on("VNT Attendance Confirm", {
	onload (frm) {
		if (frm.doc.items && frm.doc.items.length == 0) {
			frappe.msgprint(__('Không có dữ liệu để xác nhận.'));
		}
		_update_parent_status(frm);
	},
	before_save (frm) {
		frm.doc.confirm = '';
	},
	refresh(frm) {
		frm.set_df_property("items", "cannot_delete_rows", true);
		frm.set_df_property("items", "cannot_add_rows", true);
		// If current session user is the employee's mapped user and has role Leave Approver L1,
		// auto-set status to 'Đã phê duyệt' so Save will proceed even with no other changes.
		if (frm.doc && frm.doc.email && frappe.session.user === frm.doc.email && frappe.user.has_role('Leave Approver L1')) {
			frm.doc.status = 'Đã phê duyệt';
			refresh_field('status');
		}
		_update_parent_status(frm);
		_toggle_save_button(frm);
		// const grid = frm.get_field('items').grid;
		// grid.wrapper.find('.grid-static-col .icon-sm').hide();
		// grid.on('refresh', () => {
		// 	grid.wrapper.find('.grid-static-col .icon-sm').hide();
		// });
	},
	confirm (frm) {
		// If current session user is the employee's mapped user and has role Leave Approver L1,
		// assign confirm to ALL item rows (not only those with type)
		if (frm.doc && frm.doc.email && frappe.session.user === frm.doc.email && frappe.user.has_role('Leave Approver L1')) {
			(frm.doc.items || []).forEach(row => {
				frappe.model.set_value(row.doctype, row.name, "confirm", frm.doc.confirm);
			});
			refresh_field("items");
			_update_parent_status(frm);
			_toggle_save_button(frm);
			return;
		}

		// Check if the employee (mapped user) is a Leave Approver (existing logic)
		frappe.call({
			method: "vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.is_employee_leave_approver",
			args: {
				employee: frm.doc.employee,
			},
			callback(res) {
				const skip_alert = res && res.message === true;
				let missing_type = false;
				(frm.doc.items || []).forEach(row => {
					if (row.type) {
						frappe.model.set_value(row.doctype, row.name, "confirm", frm.doc.confirm);
					}
					else {
						missing_type = true;
					}
				});
				if (missing_type && !skip_alert) {
					frappe.show_alert({ message: __('Anh/chị vui lòng điền giải trình cho tất cả các ngày.'), indicator: "orange" }, 5);
				}
				refresh_field("items");
				_update_parent_status(frm);
				_toggle_save_button(frm);
			},
		});
	}
});


function _update_parent_status(frm) {
	const items = frm.doc.items || [];
	if (!items || items.length === 0) {
		frm.doc.status = 'Chờ giải trình';
		refresh_field('status');
		return;
	}
	const allType = items.every(r => Boolean(r.type));
	const allConfirm = items.every(r => Boolean(r.confirm));
	if (allConfirm) {
		frm.doc.status = 'Đã phê duyệt';
		refresh_field('status');
		return;
	}
	if (allType) {
		frm.doc.status = 'Đã giải trình';
		refresh_field('status');
		return;
	}
	frm.doc.status = 'Chờ giải trình';
	refresh_field('status');
}

function _toggle_save_button(frm) {
	const items = frm.doc.items || [];
	const allType = items.length > 0 && items.every(r => Boolean(r.type));
	const allConfirm = items.length > 0 && items.every(r => Boolean(r.confirm));
	const isEmployeeUser = frm.doc && frm.doc.email && frappe.session.user === frm.doc.email;
	const hasL1 = frappe.user.has_role('Leave Approver L1');
	const saved = !frm.is_dirty();

	const shouldHide = saved && (
		(isEmployeeUser && !hasL1 && allType) ||
		(isEmployeeUser && hasL1 && allConfirm) ||
		(!isEmployeeUser && hasL1 && allType && allConfirm)
	);

	if (shouldHide) {
		frm.disable_save();
	} else {
		frm.enable_save();
	}
}

frappe.ui.form.on('VNT Attendance Confirm Item', {
	type(frm, cdt, cdn) {
		_update_parent_status(frm);
		_toggle_save_button(frm);
	},
	confirm(frm, cdt, cdn) {
		_update_parent_status(frm);
		_toggle_save_button(frm);
	}
});

frappe.ui.form.on("VNT Attendance Confirm", "validate", function(frm) {

});
