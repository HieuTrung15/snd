// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT External Products", {
	refresh(frm) {
        frm.set_df_property("follower_name", "read_only", 1);
        frm.set_df_property("follower", "read_only", 1);
        if (frm.is_new()) {
            frm.set_value("approver_lv2", "VGT00079");
            frm.set_value("approver_lv2_name", "Phạm Văn Tân");
            frm.set_value("follower", "VGT00164");
            frappe.db.get_value("Employee", "VGT00164", ["employee_name"]).then(r => {
                if (r && r.message) {
                    frm.set_value("follower_name", r.message.employee_name || "");
                }
            });
            frappe.call({
                method: "vinatex.vnt_hr.doctype.vnt_external_products.vnt_external_products.get_employee_name",
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
                method: "vinatex.vnt_hr.doctype.vnt_external_products.vnt_external_products.get_reports_to",
                args: {
                    user: frappe.session.user
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("approver", r.message[0]);
                        frm.set_value("approver_name", r.message[1]);
                    }
                }
            });
        }
	},
});
