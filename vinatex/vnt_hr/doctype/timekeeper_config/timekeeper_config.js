// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("Timekeeper Config", {
	refresh(frm) {
        frm.add_custom_button(__('Get Data from Device'), function() {
            frappe.call({
                method: "vinatex.vinatex.doctype.overrides.chamcong.get_cham_cong",
                args: {
                },
                callback: function(r) {
                    if(r.message) {
                        console.log("a",r.message);
                    }
                }
            });
        })
	},
});
