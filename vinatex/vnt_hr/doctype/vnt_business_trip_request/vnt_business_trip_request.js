// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

// frappe.ui.form.on("VNT Business Trip Request", {
// 	refresh(frm) {

// 	},
// });
frappe.ui.form.on('VNT Business Trip Request', {
  refresh(frm) {
    if (frm.doc.creation && frm.fields_dict.created_on) {
      frm.set_value('created_on', frm.doc.creation);
    }
    if (frm.doc.modified && frm.fields_dict.last_modified_on) {
      frm.set_value('last_modified_on', frappe.datetime.str_to_user(frm.doc.modified));
    }
  }
});
