// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt
// VGT00065
frappe.ui.form.on("VNT Attendance Confirm", {
	refresh(frm) {
        frm.add_custom_button(__('Sync Timekeeper Data'), function() {
			frappe.call({
				// method: "vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.make_attendance_confirm",
				method: "vinatex.vinatex.doctype.overrides.timekeeping.get_timekeeping_data_morning",
				args: {
                    
                },
				callback: function(r) {
					console.log("r", r.message);
				}
			});
		});
		frm.set_df_property("items", "cannot_delete_rows", true);
		frm.set_df_property("items", "cannot_add_rows", true);
	}
});

frappe.ui.form.on("VNT Attendance Confirm Item", "type", function(frm, cdt, cdn) {
	const row = frappe.get_doc(cdt, cdn);
	if (!row.type) {
		frappe.msgprint({
			title: __('Thiếu thông tin'),
			message: __('Loại giải trình không được để trống.'),
			indicator: 'red'
		});
	}
});

frappe.ui.form.on("VNT Attendance Confirm", "validate", function(frm) {
	(frm.doc.items || []).forEach(function(row) {
		if (!row.type) {
			frappe.throw(__('Loại giải trình không được để trống (ngày {0}).', [frappe.format(row.date, {fieldtype: 'Date'}) || row.idx]));
		}
	});
});
