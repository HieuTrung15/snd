// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Salary Scale", {
	refresh(frm) {
        if (frm.is_new()) {
            if (!frm.doc.employee) {
                frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name")
                .then(r => r?.message?.name && frm.set_value("employee", r.message.name));
            }
            if (!frm.doc.date) {
                frm.set_value("date", frappe.datetime.now_date());
            }
        }

	},
});
