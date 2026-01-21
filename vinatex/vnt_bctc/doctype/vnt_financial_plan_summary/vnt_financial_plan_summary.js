// Copyright (c) 2026, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Financial Plan Summary", {
	refresh(frm) {
		set_default_fields(frm);
		sync_from_book(frm);
		ensure_template_lines(frm);
		set_excel_actions(frm);
	},
	template(frm) {
		handle_template_change(frm);
	},
	plan_book(frm) {
		handle_plan_book_change(frm);
	},
	fiscal_year(frm) {
		frm._prev_year_loaded = null;
		apply_previous_year_values(frm);
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

function handle_plan_book_change(frm) {
	if (!frm.doc.plan_book) {
		sync_from_book(frm, true);
		return;
	}
	frappe.db
		.get_value("VNT Financial Plan Book", frm.doc.plan_book, ["company", "fiscal_year", "template"])
		.then((r) => {
			if (!r || !r.message) {
				return;
			}
			const data = r.message;
			frm.set_value("company", data.company || frm.doc.company);
			frm.set_value("fiscal_year", data.fiscal_year || frm.doc.fiscal_year);
			frm.set_value("template", data.template || frm.doc.template);
		})
		.then(() => {
			handle_template_change(frm);
		});
}

function sync_from_book(frm, clear_only) {
	if (!frm.doc.plan_book) {
		if (clear_only) {
			frm._plan_book_loaded = null;
		}
		return;
	}
	if (frm._plan_book_loaded === frm.doc.plan_book) {
		return;
	}
	handle_plan_book_change(frm);
	frm._plan_book_loaded = frm.doc.plan_book;
}

function load_template_items(frm) {
	frappe.call({
		method:
			"vinatex.vnt_bctc.doctype.vnt_financial_plan_summary.vnt_financial_plan_summary.get_template_items",
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
				row.item_code = item.item_code;
			});
			frm.refresh_field("lines");
			apply_previous_year_values(frm);
		},
	});
}

function ensure_template_lines(frm) {
	if (!frm.doc.template) {
		return;
	}
	if ((frm.doc.lines || []).length) {
		frm._template_loaded = frm.doc.template;
		apply_previous_year_values(frm);
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

function set_excel_actions(frm) {
	if (frm.is_new()) {
		return;
	}
	frm.clear_custom_buttons();
	frm.add_custom_button(__("Tải Excel"), () => download_excel(frm));
	frm.add_custom_button(__("Nhập Excel"), () => import_excel(frm));
}

function download_excel(frm) {
	const url = frappe.urllib.get_full_url(
		`/api/method/vinatex.vnt_bctc.doctype.vnt_financial_plan_summary.vnt_financial_plan_summary.download_plan_summary_excel?docname=${encodeURIComponent(
			frm.doc.name
		)}`
	);
	window.open(url);
}

function import_excel(frm) {
	frappe.prompt(
		[
			{
				fieldname: "file_url",
				label: __("Tệp Excel"),
				fieldtype: "Attach",
				reqd: 1,
			},
		],
		(values) => {
			frappe.call({
				method:
					"vinatex.vnt_bctc.doctype.vnt_financial_plan_summary.vnt_financial_plan_summary.import_plan_summary_excel",
				args: {
					docname: frm.doc.name,
					file_url: values.file_url,
				},
				freeze: true,
				callback: () => {
					frm.reload_doc();
				},
			});
		},
		__("Nhập Excel"),
		__("Nhập")
	);
}

function apply_previous_year_values(frm) {
	if (!frm.is_new()) {
		return;
	}
	if (frm._prev_year_loaded) {
		return;
	}
	if (!frm.doc.company || !frm.doc.template || !frm.doc.fiscal_year) {
		return;
	}
	if (!frm.doc.lines || !frm.doc.lines.length) {
		return;
	}
	if (has_existing_values(frm.doc.lines)) {
		frm._prev_year_loaded = true;
		return;
	}

	frm._prev_year_loaded = true;
	frappe.call({
		method:
			"vinatex.vnt_bctc.doctype.vnt_financial_plan_summary.vnt_financial_plan_summary.get_previous_plan_summary_values",
		args: {
			company: frm.doc.company,
			template: frm.doc.template,
			fiscal_year: frm.doc.fiscal_year,
			plan_book: frm.doc.plan_book,
		},
		callback: (r) => {
			const source_lines = (r && r.message && r.message.lines) || [];
			if (!source_lines.length) {
				return;
			}
			const source_map = build_source_map(source_lines);
			(frm.doc.lines || []).forEach((line) => {
				const source = find_source_line(source_map, line);
				if (!source) {
					return;
				}
				Object.keys(PREV_FIELD_MAP).forEach((prev_field) => {
					const current_field = PREV_FIELD_MAP[prev_field];
					const value = source[current_field];
					if (value !== null && value !== undefined && value !== "") {
						line[prev_field] = value;
					}
				});
			});
			frm.refresh_field("lines");
		},
	});
}

function build_source_map(lines) {
	const map = {};
	lines.forEach((line) => {
		if (line.item_code) {
			map[`code::${line.item_code}`] = line;
		}
		const key = build_line_key(line);
		if (key) {
			map[`key::${key}`] = line;
		}
	});
	return map;
}

function find_source_line(map, line) {
	if (line.item_code) {
		const by_code = map[`code::${line.item_code}`];
		if (by_code) {
			return by_code;
		}
	}
	const key = build_line_key(line);
	if (!key) {
		return null;
	}
	return map[`key::${key}`] || null;
}

function build_line_key(line) {
	const parts = [
		normalize_text(line.doi_tuong),
		normalize_text(line.ct_doi_tuong),
		normalize_text(line.chi_tiet_doi_tuong_c2),
		normalize_text(line.khoan_muc),
		normalize_text(line.ct),
	];
	return parts.join("||");
}

function normalize_text(value) {
	const text = (value || "").toString().trim().toLowerCase();
	return text
		.normalize("NFD")
		.replace(/[\u0300-\u036f]/g, "")
		.replace(/\s+/g, " ");
}

function has_existing_values(lines) {
	return lines.some((line) =>
		NUMERIC_FIELDS.some((field) => line[field] !== null && line[field] !== undefined && line[field] !== "")
	);
}

const PREV_FIELD_MAP = {
	prev_plan: "current_plan",
	prev_3t: "current_3t",
	prev_6t: "current_6t",
	prev_9t: "current_9t",
	prev_12t: "current_12t",
};

Array.from({ length: 12 }, (_, i) => `prev_t${String(i + 1).padStart(2, "0")}`).forEach((field, idx) => {
	PREV_FIELD_MAP[field] = `current_t${String(idx + 1).padStart(2, "0")}`;
});

const NUMERIC_FIELDS = [
	...Object.keys(PREV_FIELD_MAP),
	...Object.values(PREV_FIELD_MAP),
	"luy_ke",
];
