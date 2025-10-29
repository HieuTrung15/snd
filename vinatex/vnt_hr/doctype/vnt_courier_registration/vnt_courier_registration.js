// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Courier Registration", {
	refresh(frm) {
        if (frm.is_new()) {
            frm.set_value("date", frappe.datetime.get_today());
            frappe.call({
                method: "vinatex.vnt_hr.doctype.vnt_courier_registration.vnt_courier_registration.get_employee_name",
                args: {
                    user: frappe.session.user
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("employee", r.message);
                    }
                }
            });
            frappe.call({
                method: "vinatex.vnt_hr.doctype.vnt_courier_registration.vnt_courier_registration.get_reports_to",
                args: {
                    user: frappe.session.user
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("lead_department", r.message);
                    }
                }
            });
        }
	},
});


frappe.ui.form.on("VNT Courier Registration Item", {
    supplier(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        frappe.call({
            method: "vinatex.vnt_hr.doctype.vnt_courier_registration.vnt_courier_registration.get_supplier_address",
            args: {
                supplier: row.supplier
            },
            callback: function (r) {
                if (r.message) {             
                    row.addr = r.message;
                }
                frm.refresh_field("items");
            }
        });
    }
});