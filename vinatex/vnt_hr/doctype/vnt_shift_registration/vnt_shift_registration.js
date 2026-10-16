// Copyright (c) 2026, vinatex and contributors
// For license information, please see license.txt

const KIP_TIME_MAP = {
	"Sáng (06:00-14:00)": ["06:00:00", "14:00:00"],
	"Chiều (14:00-22:00)": ["14:00:00", "22:00:00"],
	"Đêm (22:00-06:00)": ["22:00:00", "06:00:00"],
	"HC (07:30-16:30)": ["07:30:00", "16:30:00"],
};

frappe.ui.form.on("VNT Shift Registration", {
	kip(frm) {
		if (!frm.doc.kip) return;
		const times = KIP_TIME_MAP[frm.doc.kip];
		if (!times) return;
		frm.set_value("from_time", times[0]);
		frm.set_value("to_time", times[1]);
	},
});
