// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT External Products", {
    after_save(frm) {
        // Chỉ auto chạy 1 lần khi còn ở state "Mới tạo"
        if (frm.doc.workflow_state === "Mới tạo") {
            frappe.call({
                method: "frappe.model.workflow.apply_workflow",
                args: {
                    doc: frm.doc,
                    action: "Chuyển duyệt", // action trong workflow
                },
                callback() {
                    frm.reload_doc();
                }
            });
        }
    },
    // VGT0175 - Quý
	refresh(frm) {
        frm.set_df_property("follower_name", "read_only", 1);
        frm.set_df_property("follower", "read_only", 1);
        if (frm.is_new()) {
            frm.set_value("approver_lv2", "VGT00083");
            frm.set_value("approver_lv2_name", "Nguyễn Thị Thu Hiền");
            frm.set_value("follower", "VGT00175");
            frappe.db.get_value("Employee", "VGT00175", ["employee_name"]).then(r => {
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
	is_all(frm) {
        const targetValue = frappe.utils.cint(frm.doc.is_all);
        if (!frm.doc.list_items || !frm.doc.list_items.length) {
            return;
        }
        frm.doc.list_items.forEach(row => {
            frappe.model.set_value(row.doctype, row.name, "is_export", targetValue);
        });
        frm.refresh_field("list_items");
	},
});
