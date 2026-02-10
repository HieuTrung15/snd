// Copyright (c) 2026, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Fabric Technology", {
	refresh(frm) {
        if (!frm.doc.employee) {
            frm.set_value("employee", frappe.session.user);
        }
        if (!frm.doc.date) {
            frm.set_value("date", frappe.datetime.get_today());
        }
	},
    
});
