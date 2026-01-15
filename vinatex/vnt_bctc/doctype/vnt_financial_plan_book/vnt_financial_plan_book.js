// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Financial Plan Book", {
	refresh(frm) {
		set_default_fields(frm);
		ensure_template_lines(frm);
	},
	template(frm) {
		handle_template_change(frm);
	},
});

function set_default_fields(frm) {
	if (!frm.is_new()) {
		return;
	}
	set_default_fiscal_year(frm);
	set_default_template(frm);
}

function set_default_fiscal_year(frm) {
	if (frm.doc.fiscal_year) {
		return;
	}
	const today = frappe.datetime.nowdate();
	frappe.db
		.get_list("Fiscal Year", {
			filters: {
				year_start_date: ["<=", today],
				year_end_date: [">=", today],
			},
			fields: ["name", "year_start_date"],
			order_by: "year_start_date desc",
			limit: 1,
		})
		.then((rows) => {
			if (rows && rows.length && !frm.doc.fiscal_year) {
				frm.set_value("fiscal_year", rows[0].name);
				return;
			}
			return frappe.db.get_list("Fiscal Year", {
				fields: ["name", "year_start_date"],
				order_by: "year_start_date desc",
				limit: 1,
			});
		})
		.then((rows) => {
			if (rows && rows.length && !frm.doc.fiscal_year) {
				frm.set_value("fiscal_year", rows[0].name);
			}
		});
}

function set_default_template(frm) {
	if (frm.doc.template) {
		return;
	}
	frappe.db
		.get_list("VNT Financial Report Template", {
			filters: { is_active: 1 },
			fields: ["name"],
			order_by: "creation desc",
			limit: 1,
		})
		.then((rows) => {
			if (rows && rows.length && !frm.doc.template) {
				frm.set_value("template", rows[0].name);
			}
		});
}

function load_template_items(frm) {
	frappe.call({
		method: "vinatex.vnt_bctc.doctype.vnt_financial_plan_book.vnt_financial_plan_book.get_template_items",
		args: { template: frm.doc.template },
		callback: (r) => {
			const items = r.message || [];
			frm.clear_table("lines");
			items.forEach((item) => {
				const row = frm.add_child("lines");
				row.doi_tuong = item.doi_tuong;
				row.ct_doi_tuong = item.ct_doi_tuong;
				row.chi_tiet_doi_tuong_c2 = item.chi_tiet_doi_tuong_c2;
				row.khoan_muc = item.khoan_muc;
				row.ct = item.ct;
			});
			frm.refresh_field("lines");
		},
	});
}

function ensure_template_lines(frm) {
	if (!frm.doc.template) {
		return;
	}
	if ((frm.doc.lines || []).length) {
		frm._template_loaded = frm.doc.template;
		return;
	}
	load_template_items(frm);
	frm._template_loaded = frm.doc.template;
}

function handle_template_change(frm) {
	if (!frm.doc.template) {
		frm.clear_table("lines");
		frm.refresh_field("lines");
		frm._template_loaded = null;
		return;
	}

	if (frm._template_loaded === frm.doc.template) {
		return;
	}

	frm.clear_table("lines");
	frm.refresh_field("lines");
	load_template_items(frm);
	frm._template_loaded = frm.doc.template;
}
