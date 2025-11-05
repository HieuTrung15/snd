// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Salary Slip", {
	onload(frm) {
		set_rendered_html(frm);
	},
	refresh(frm) {
		set_rendered_html(frm);
	},
});

function set_rendered_html(frm) {
	if (!frm || !frm.fields_dict?.html) return;
	const target = frm.fields_dict.html.$wrapper;
	if (!target || !target.length) return;
	const content = frm.doc.rendered_html || "";
	target.html(content);
}
