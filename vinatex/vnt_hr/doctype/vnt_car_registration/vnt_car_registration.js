// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Car Registration", {
	 refresh(frm) {
        if (!frm.doc.employee) {
            frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
            .then(r => {
                if (r && r.message && r.message.name) {
                    frm.set_value("employee", r.message.name);
                }
            });
            
        }
	},
});
