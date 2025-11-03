// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Meeting Room Booking", {
	refresh(frm) {
		if (frm.is_new()) {
			frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
				.then(r => {
					if (r && r.message && r.message.name) {
						frm.set_value("employee", r.message.name);
					}
				});
			frappe.call({
                method: "vinatex.vnt_hr.doctype.vnt_meeting_room_booking.vnt_meeting_room_booking.get_reports_to",
                args: {
                    'user': frappe.session.user
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("approver_name", r.message);
                    }
                }
            });
			frm.set_value("date", frappe.datetime.get_today());
		}
	},
});
