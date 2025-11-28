frappe.ui.form.on("Job Requisition", {
    refresh(frm) {
        if (!frm.doc.requested_by) {
            frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name")
            .then(r => r?.message?.name && frm.set_value("requested_by", r.message.name));
        }
    }

});