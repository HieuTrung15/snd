// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

// frappe.ui.form.on("VNT Business Trip Request", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on('VNT Business Trip Request', {
//   refresh(frm) {
//     if (frm.doc.creation && frm.fields_dict.created_on) {
//       frm.set_value('created_on', frm.doc.creation);
//     }
//     if (frm.doc.modified && frm.fields_dict.last_modified_on) {
//       frm.set_value('last_modified_on', frappe.datetime.str_to_user(frm.doc.modified));
    
//   }
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
            if (!frm.doc.date) {
                frm.set_value("created_on", frappe.datetime.get_today());
            }
    },
    refresh(frm) {
        frm.add_custom_button(__('Sync'), function() {
            frappe.call({
                method: "vinatex.vnt_hr.doctype.vnt_business_trip_request.vnt_business_trip_request.allocate_leave_for_all",
                // method: "vinatex.vinatex.doctype.overrides.timekeeping.get_timekeeping_data",
                // args: {
                //     "year": 2025,
                //     "month": 9,
                //     "employee": "VGT00065"
                // },
                callback: function(r) {
                    console.log("r", r.message);
                }
            });
        });
    },
});
