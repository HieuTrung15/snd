// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Car Registration", {
    onload (frm) {
        frm.set_query("driver", function (doc) {
            return {
                filters: {
                    custom_driver: 1
                }
            };
        });
    },
	 refresh(frm) {
        if (frm.is_new()) {
            frappe.call({
                method: "vinatex.vnt_hr.doctype.vnt_car_registration.vnt_car_registration.get_employee_name",
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
                method: "vinatex.vnt_hr.doctype.vnt_car_registration.vnt_car_registration.get_reports_to",
                args: {
                    user: frappe.session.user
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("approver", r.message);
                    }
                }
            });
        }
	},
});
