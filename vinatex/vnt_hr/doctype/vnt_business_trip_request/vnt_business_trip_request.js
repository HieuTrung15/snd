// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on('VNT Business Trip Request', {
    onload(frm) {
        // tự động lấy user khi tạo phiếu
        if (!frm.doc.employee) {
            frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
            .then(r => {
                if (r && r.message && r.message.name) {
                    frm.set_value("employee", r.message.name);
                }
            });
        }
        // tự động lấy date là ngày tạo phiếu
        // if (!frm.doc.date) {
        //     frm.set_value("created_on", frappe.datetime.get_today());
        // }
    }
});
