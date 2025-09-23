frappe.ui.form.on("Employee", {
    department(frm) {
        if (frm.doc.department) {
            frappe.call({
                method: "vinatex.vinatex.doctype.overrides.employee.get_approver_by_department",
                args: {
                    department: frm.doc.department
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value("leave_approver", r.message);
                    } else {
                        frm.set_value("leave_approver", null);
                    }
                }
            });
        }
    }
});