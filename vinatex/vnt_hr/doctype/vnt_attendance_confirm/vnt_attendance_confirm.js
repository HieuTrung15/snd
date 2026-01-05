// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt
// VGT00065
frappe.ui.form.on("VNT Attendance Confirm", {
	onload (frm) {
		if (frm.doc.items && frm.doc.items.length == 0) {
			frappe.msgprint(__('Không có dữ liệu để xác nhận.'));
		}	
	},
	before_save (frm) {
		frm.doc.confirm = '';
	},
	refresh(frm) {
		frm.set_df_property("items", "cannot_delete_rows", true);
		frm.set_df_property("items", "cannot_add_rows", true);
		// const grid = frm.get_field('items').grid;
		// grid.wrapper.find('.grid-static-col .icon-sm').hide();
		// grid.on('refresh', () => {
		// 	grid.wrapper.find('.grid-static-col .icon-sm').hide();
		// });
	},
	confirm (frm) {
		// Check if the employee is a Leave Approver
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
			},
		});
	}
});

frappe.ui.form.on("VNT Attendance Confirm", "validate", function(frm) {

});
