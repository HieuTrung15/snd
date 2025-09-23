// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt
// VGT00065
frappe.ui.form.on("VNT Attendance Confirm", {
	refresh(frm) {
        frm.add_custom_button(__('Sync Timekeeper Data'), function() {
			frappe.call({
				method: "vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.make_attendance_confirm",
				// method: "vinatex.vinatex.doctype.overrides.timekeeping.get_timekeeping_data",
				args: {
                    
                },
				callback: function(r) {
					console.log("r", r.message);
				}
			});
		});
	},
});
