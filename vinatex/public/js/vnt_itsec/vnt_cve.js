frappe.ui.form.on("VNT CVE", {
	refresh(frm) {
		if (frm.is_new() || !frm.doc.cve_id) {
			return;
		}
		frm.add_custom_button(__("Open NVD"), () => {
			const url = `https://nvd.nist.gov/vuln/detail/${frm.doc.cve_id}`;
			window.open(url, "_blank", "noopener");
		});
	},
});
