frappe.ui.form.on("VNT Applicant Headhunter Rating", {
	form_render(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row) return;
		row.headhunter = row.headhunter || frappe.session.user;
	},
});
