// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT External Products List", {
	refresh(frm) {
		apply_child_defaults(frm);
	},

	list_items_add(frm, cdt, cdn) {
		set_child_defaults(frm, cdt, cdn);
		frm.refresh_field("list_items");
	},

	before_save(frm) {
		apply_child_defaults(frm);
	},
});

function apply_child_defaults(frm) {
	(frm.doc.list_items || []).forEach((row) => {
		if (!row) {
			return;
		}
		set_child_defaults(frm, row.doctype, row.name);
	});
	frm.refresh_field("list_items");
}

function set_child_defaults(frm, cdt, cdn) {
	const row = locals[cdt]?.[cdn];
	if (!row) {
		return;
	}

	const code = frm.doc.name || frm.doc.item_code;
	if (code) {
		row.item_code = code;
	}

	if (frm.doc.item_name && !row.item_name) {
		row.item_name = frm.doc.item_name;
	}

	if (frm.doc.unit && !row.unit) {
		row.unit = frm.doc.unit;
	}

	const currentQty = frm.doc.qty_current;
	if ((currentQty || currentQty === 0) && !row.qty_current) {
		row.qty_current = currentQty;
	}

	if (!row.type) {
		row.type = "Nhập";
	}
}
