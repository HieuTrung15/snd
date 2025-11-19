// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Salary Slip", {
	onload(frm) {
		vntSetRenderedHtml(frm);
		vntUpdateAllowanceTotals(frm);
	},
	refresh(frm) {
		vntSetRenderedHtml(frm);
		vntUpdateAllowanceTotals(frm);
	},
	items_add(frm) {
		vntUpdateAllowanceTotals(frm);
	},
	items_remove(frm) {
		vntUpdateAllowanceTotals(frm);
	},
});

frappe.ui.form.on("VNT Salary Slip Item", {
	amount(frm, cdt, cdn) {
		vntRecalculateAllowanceRow(cdt, cdn);
		vntUpdateAllowanceTotals(frm);
	},
	so_thang(frm, cdt, cdn) {
		vntRecalculateAllowanceRow(cdt, cdn);
		vntUpdateAllowanceTotals(frm);
	},
	thue_tncn(frm, cdt, cdn) {
		vntRecalculateAllowanceRow(cdt, cdn);
		vntUpdateAllowanceTotals(frm);
	},
	tong(frm) {
		vntUpdateAllowanceTotals(frm);
	},
	thuc_linh(frm) {
		vntUpdateAllowanceTotals(frm);
	},
});

function vntSetRenderedHtml(frm) {
	if (!frm || !frm.fields_dict?.html) return;
	const target = frm.fields_dict.html.$wrapper;
	if (!target || !target.length) return;
	const content = frm.doc.rendered_html || "";
	target.html(content);
}

function vntUpdateAllowanceTotals(frm) {
	if (!frm || !frm.doc || frm.doc.docstatus > 0) {
		return;
	}

	const rows = Array.isArray(frm.doc.items) ? frm.doc.items : [];
	let totalAllowance = 0;
	let totalTax = 0;
	let totalNet = 0;

	rows.forEach((row) => {
		totalAllowance += vntToNumber(row?.tong);
		totalTax += vntToNumber(row?.thue_tncn);
		totalNet += vntToNumber(row?.thuc_linh);
	});

	vntSetParentValue(frm, "tong_phu_cap", totalAllowance);
	vntSetParentValue(frm, "tong_thue_tncn_phu_cap", totalTax);
	vntSetParentValue(frm, "tong_thuc_linh_phu_cap", totalNet);
}

function vntSetParentValue(frm, fieldname, value) {
	if (!frm || !fieldname) return;
	const current = vntToNumber(frm.doc[fieldname]);
	if (Math.abs(current - value) > 0.0001) {
		frm.set_value(fieldname, value);
	}
}

function vntToNumber(value) {
	const number = parseFloat(value);
	return Number.isFinite(number) ? number : 0;
}

function vntRecalculateAllowanceRow(cdt, cdn) {
	if (!cdt || !cdn || !locals?.[cdt]?.[cdn]) {
		return;
	}
	const row = locals[cdt][cdn];
	const months = Math.max(vntToNumber(row.so_thang), 0);
	const amount = vntToNumber(row.amount);
	const total = months * amount;
	const tax = Math.min(total, Math.max(vntToNumber(row.thue_tncn), 0));
	const net = total - tax;

	frappe.model.set_value(cdt, cdn, "tong", total || 0);
	frappe.model.set_value(cdt, cdn, "thuc_linh", net || 0);
}
