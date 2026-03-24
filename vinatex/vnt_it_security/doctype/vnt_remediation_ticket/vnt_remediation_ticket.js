// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

const VNT_REMEDIATION_STATUS_COLORS = {
	Open: "red",
	Assigned: "orange",
	"In Progress": "yellow",
	Waiting: "gray",
	Done: "green",
	Rejected: "darkgrey",
};

function vntGetRemediationIndicator(status) {
	const normalized = (status || "").trim();
	const color = VNT_REMEDIATION_STATUS_COLORS[normalized] || "gray";
	return [__(normalized || "Unknown"), color, `status,=,${normalized}`];
}

frappe.ui.form.on("VNT Remediation Ticket", {
	refresh(frm) {
		const [label, color] = vntGetRemediationIndicator(frm.doc.status);
		frm.dashboard.clear_headline();
		frm.dashboard.add_indicator(label, color);
	},
});

frappe.listview_settings["VNT Remediation Ticket"] = {
	get_indicator(doc) {
		return vntGetRemediationIndicator(doc.status);
	},
};
