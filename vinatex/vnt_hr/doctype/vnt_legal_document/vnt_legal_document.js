// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Legal Document", {
	attach(frm) {
        if (frm.doc.attach) {
            const file_url = frm.doc.attach;

            if (file_url.toLowerCase().endsWith(".pdf")) {
            const html = `
                <iframe src="${file_url}" width="100%" height="600px"
                style="border:1px solid #ccc;border-radius:8px;"></iframe>
            `;
            frm.fields_dict.html.$wrapper.html(html);
            } else {
            frm.fields_dict.html.$wrapper.html(
                `<p><i>File này không phải PDF. Vui lòng tải file PDF để xem trực tiếp.</i></p>`
            );
            }
        } 
        else {
            frm.fields_dict.html.$wrapper.html("<p><i>Chưa có file nào được tải lên.</i></p>");
        }
    },

    refresh(frm) {
        if (frm.doc.attach) frm.trigger("attach");
        if (!frm.doc.employee) {
            frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
            .then(r => {
                if (r && r.message && r.message.name) {
                    frm.set_value("employee", r.message.name);
                }
            });        
        };
        if (!frm.doc.date) {
            frm.set_value("date", frappe.datetime.get_today());
        };
    }
});
