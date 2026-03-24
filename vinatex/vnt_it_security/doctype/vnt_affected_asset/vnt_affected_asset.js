// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

const VNT_AFFECTED_STATUS_COLORS = {
	Open: "red",
	"In Progress": "yellow",
	Mitigated: "green",
	Patched: "green",
	"Not Applicable": "blue",
	"Accepted Risk": "darkgrey",
};

function vntGetAffectedIndicator(status) {
	const normalized = (status || "").trim();
	const color = VNT_AFFECTED_STATUS_COLORS[normalized] || "gray";
	return [__(normalized || "Unknown"), color, `status,=,${normalized}`];
}

frappe.ui.form.on("VNT Affected Asset", {
	refresh(frm) {
		const [label, color] = vntGetAffectedIndicator(frm.doc.status);
		frm.dashboard.clear_headline();
		frm.dashboard.add_indicator(label, color);
	},
});

frappe.listview_settings["VNT Affected Asset"] = {
	get_indicator(doc) {
		return vntGetAffectedIndicator(doc.status);
	},
};
