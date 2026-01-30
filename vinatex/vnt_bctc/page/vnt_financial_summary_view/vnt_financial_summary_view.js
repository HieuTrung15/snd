frappe.pages["vnt-financial-summary-view"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Tổng hợp BCTC"),
		single_column: true,
	});

	const state = {
		doc: null,
		year_info: null,
		doctype: "VNT Financial Plan Summary",
		controls: {},
	};

	page.set_primary_action(__("Lưu"), () => save_doc(page, state));

	$(page.main).html(`
		<div class="vnt-bctc-summary-view">
			<div class="vnt-bctc-summary-shell">
				<div class="vnt-bctc-filters"></div>
				<div class="vnt-bctc-summary-meta text-muted"></div>
				<div class="vnt-bctc-summary-body"></div>
			</div>
		</div>
	`);

	render_filters(page, state);
	inject_styles(page);
	set_empty_state(page);
};

function render_filters(page, state) {
	const $filters = $(page.main).find(".vnt-bctc-filters");
	$filters.html(`
		<div class="vnt-bctc-filter-row">
			<div class="vnt-bctc-filter-group"></div>
			<div class="vnt-bctc-filter-actions">
				<button class="btn btn-default btn-sm vnt-bctc-download" type="button">${__("Tải Excel")}</button>
				<button class="btn btn-default btn-sm vnt-bctc-import" type="button">${__("Nhập Excel")}</button>
			</div>
		</div>
	`);
	const $group = $filters.find(".vnt-bctc-filter-group");

	const type_control = frappe.ui.form.make_control({
		df: {
			fieldname: "summary_type",
			label: __("Loại dữ liệu"),
			fieldtype: "Select",
			options: "Kế hoạch\nThực tế",
			default: "Kế hoạch",
			reqd: 1,
			change() {
				const value = type_control.get_value();
				state.doctype = value === "Thực tế" ? "VNT Financial Actual Summary" : "VNT Financial Plan Summary";
				update_doc_control(state);
				set_empty_state(page);
			},
		},
		parent: $group,
		render_input: true,
	});
	type_control.make();
	state.controls.type = type_control;

	const doc_control = frappe.ui.form.make_control({
		df: {
			fieldname: "summary_doc",
			label: __("Bảng tổng hợp"),
			fieldtype: "Link",
			options: state.doctype,
			reqd: 1,
			change() {
				load_doc(page, state);
			},
		},
		parent: $group,
		render_input: true,
	});
	doc_control.make();
	doc_control.$input.on("change", () => load_doc(page, state));
	state.controls.doc = doc_control;

	$filters.find(".vnt-bctc-download").on("click", () => download_excel(state));
	$filters.find(".vnt-bctc-import").on("click", () => import_excel(page, state));
}

function update_doc_control(state) {
	const doc_control = state.controls.doc;
	if (!doc_control) {
		return;
	}
	doc_control.df.options = state.doctype;
	doc_control.set_value("");
	doc_control.refresh();
	state.doc = null;
	state.year_info = null;
	state.original_lines = null;
}

function load_doc(page, state) {
	const control = state.controls.doc;
	const docname = control ? control.get_value() : null;
	if (!docname) {
		state.doc = null;
		state.year_info = null;
		state.original_lines = null;
		set_empty_state(page);
		return;
	}

	frappe.call({
		method: "frappe.client.get",
		args: {
			doctype: state.doctype,
			name: docname,
		},
		freeze: true,
		callback: (r) => {
			if (!r || !r.message) {
				return;
			}
			state.doc = r.message;
			state.original_lines = snapshot_lines(state.doc.lines || []);
			load_year_info(state.doc.fiscal_year).then((year_info) => {
				state.year_info = year_info;
				render_doc(page, state);
			});
		},
	});
}

function load_year_info(fiscal_year) {
	if (!fiscal_year) {
		return Promise.resolve(null);
	}
	return frappe.db
		.get_value("Fiscal Year", fiscal_year, "year_start_date")
		.then((r) => {
			const start_date = r && r.message ? r.message.year_start_date : null;
			if (!start_date) {
				return null;
			}
			const year = new Date(start_date).getFullYear();
			if (!year) {
				return null;
			}
			return { current_year: year, prev_year: year - 1 };
		});
}

function render_doc(page, state) {
	const $meta = $(page.main).find(".vnt-bctc-summary-meta");
	const $body = $(page.main).find(".vnt-bctc-summary-body");

	if (!state.doc) {
		set_empty_state(page);
		return;
	}

	$meta.html(`
		<div class="vnt-bctc-summary-card">
			<div class="vnt-bctc-summary-title">${escape_html(state.doc.name)}</div>
			<div class="vnt-bctc-summary-grid">
				<div>
					<div class="vnt-bctc-summary-label">${__("Công ty")}</div>
					<div class="vnt-bctc-summary-value">${escape_html(state.doc.company || "-")}</div>
				</div>
				<div>
					<div class="vnt-bctc-summary-label">${__("Năm tài chính")}</div>
					<div class="vnt-bctc-summary-value">${escape_html(state.doc.fiscal_year || "-")}</div>
				</div>
				<div>
					<div class="vnt-bctc-summary-label">${__("Mẫu báo cáo")}</div>
					<div class="vnt-bctc-summary-value">${escape_html(state.doc.template || "-")}</div>
				</div>
			</div>
		</div>
	`);

	if (!state.year_info) {
		$body.html(`<div class="text-muted">${__("Không xác định được năm tài chính.")}</div>`);
		return;
	}

	const headers = build_headers(state.year_info.prev_year, state.year_info.current_year);
	const lines = state.doc.lines || [];

	let rows_html = "";
	lines.forEach((line, index) => {
		const cells = build_row_cells(line, index);
		rows_html += `<tr>${cells}</tr>`;
	});

	if (!rows_html) {
		rows_html = `<tr><td colspan="${headers.length}" class="text-muted">${__("Không có dữ liệu")}</td></tr>`;
	}

	const header_html = headers.map((label) => `<th>${escape_html(label)}</th>`).join("");
	$body.html(`
		<div class="table-responsive">
			<table class="table table-bordered table-hover vnt-bctc-summary-table">
				<thead><tr>${header_html}</tr></thead>
				<tbody>${rows_html}</tbody>
			</table>
		</div>
	`);
	bind_input_events(page, state);
}

function build_headers(prev_year, current_year) {
	const prev_suffix = String(prev_year).slice(-2);
	const current_suffix = String(current_year).slice(-2);
	const headers = [
		"Nhóm to",
		"Nhóm",
		"Chi tiết đối tượng",
		"Chi tiết đối tượng cấp 2",
		"Khoản mục",
		"Chi tiết khoản mục",
		"Mã khoản mục",
		`KH${prev_year}`,
		`3T.${prev_suffix}`,
		`6T.${prev_suffix}`,
		`9T.${prev_suffix}`,
		`12T.${prev_suffix}`,
		`KH${current_year}`,
		`3T.${current_suffix}`,
		`6T.${current_suffix}`,
		`9T.${current_suffix}`,
		`12T.${current_suffix}`,
	];
	for (let month = 1; month <= 12; month += 1) {
		headers.push(`T${String(month).padStart(2, "0")}.${prev_suffix}`);
	}
	for (let month = 1; month <= 12; month += 1) {
		headers.push(`T${String(month).padStart(2, "0")}.${current_suffix}`);
	}
	headers.push("Lũy kế");
	return headers;
}

function build_row_cells(line, index) {
	const cells = [
		escape_html(line.nhom_to || ""),
		escape_html(line.doi_tuong || ""),
		escape_html(line.ct_doi_tuong || ""),
		escape_html(line.chi_tiet_doi_tuong_c2 || ""),
		escape_html(line.khoan_muc || ""),
		escape_html(line.ct || ""),
		escape_html(line.item_code || ""),
	];

	NUMERIC_FIELDS.forEach((field) => {
		const value = line[field];
		cells.push(
			`<input type="text" class="form-control input-xs text-right" data-row-idx="${index}" data-field="${field}" value="${format_number(
				value
			)}" />`
		);
	});

	return cells.map((value) => `<td>${value}</td>`).join("");
}

function set_empty_state(page) {
	const $meta = $(page.main).find(".vnt-bctc-summary-meta");
	const $body = $(page.main).find(".vnt-bctc-summary-body");
	$meta.html("");
	$body.html(
		`<div class="text-muted vnt-bctc-summary-empty">${__("Chọn loại dữ liệu và bảng tổng hợp để xem dữ liệu.")}</div>`
	);
}

function format_number(value) {
	if (value === null || value === undefined || value === "" || Number(value) === 0) {
		return "";
	}
	const number = Number(value);
	if (Number.isNaN(number)) {
		return "";
	}
	if (typeof frappe.format_number === "function") {
		return frappe.format_number(number, null, NUMBER_PRECISION);
	}
	return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: NUMBER_PRECISION }).format(number);
}

function escape_html(value) {
	const safe = value === null || value === undefined ? "" : value;
	return frappe.utils.escape_html(safe);
}

function inject_styles(page) {
	$(page.head || page.wrapper).append(`
		<style>
			:root {
				--vnt-surface: #f0f4fb;
				--vnt-card: #f8fbff;
				--vnt-border: #d4dceb;
				--vnt-text: #1f2a3d;
				--vnt-muted: #6b778c;
				--vnt-accent: #1f6feb;
				--vnt-table-header: #e7eef9;
				--vnt-row-hover: #dde9fb;
			}
			.vnt-bctc-summary-view .table-responsive {
				max-height: 75vh;
			}
			.vnt-bctc-summary-shell {
				background: #ffffff;
				border-radius: 16px;
				padding: 18px 20px 22px;
				box-shadow: 0 10px 24px rgba(31, 42, 61, 0.12);
				border: 1px solid var(--vnt-border);
			}
			.vnt-bctc-summary-view th,
			.vnt-bctc-summary-view td {
				white-space: nowrap;
				vertical-align: middle;
			}
			.vnt-bctc-summary-view input.form-control {
				min-width: 110px;
			}
			.vnt-bctc-filter-row {
				display: flex;
				gap: 16px;
				align-items: flex-end;
				flex-wrap: wrap;
			}
			.vnt-bctc-filter-group {
				display: flex;
				gap: 16px;
				flex: 1 1 auto;
				min-width: 320px;
				align-items: flex-end;
			}
			.vnt-bctc-filter-group .form-group {
				margin-bottom: 0;
				flex: 1 1 280px;
			}
			.vnt-bctc-filter-group .form-group:first-child {
				flex: 2 1 420px;
				min-width: 360px;
			}
			.vnt-bctc-filter-actions {
				display: flex;
				gap: 8px;
				align-items: center;
			}
			.vnt-bctc-summary-card {
				background: var(--vnt-card);
				border: 1px solid var(--vnt-border);
				border-radius: 10px;
				padding: 14px 18px;
				margin: 12px 0 18px;
				box-shadow: 0 6px 16px rgba(31, 42, 61, 0.08);
			}
			.vnt-bctc-summary-title {
				font-size: 18px;
				font-weight: 600;
				color: var(--vnt-text);
				margin-bottom: 6px;
			}
			.vnt-bctc-summary-grid {
				display: grid;
				gap: 12px;
				grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
			}
			.vnt-bctc-summary-label {
				font-size: 12px;
				text-transform: uppercase;
				letter-spacing: 0.04em;
				color: var(--vnt-muted);
			}
			.vnt-bctc-summary-value {
				font-size: 14px;
				color: var(--vnt-text);
				font-weight: 500;
			}
			.vnt-bctc-summary-table thead th {
				background: var(--vnt-table-header);
				border-bottom: 2px solid var(--vnt-border);
				position: sticky;
				top: 0;
				z-index: 1;
			}
			.vnt-bctc-summary-table tbody tr:nth-child(even) {
				background: #f9fbff;
			}
			.vnt-bctc-summary-table tbody tr:hover {
				background: var(--vnt-row-hover);
			}
			.vnt-bctc-summary-view input.form-control {
				border-radius: 8px;
				border: 1px solid var(--vnt-border);
				background: #fff;
				padding: 4px 8px;
				box-shadow: inset 0 1px 2px rgba(31, 42, 61, 0.08);
			}
			.vnt-bctc-summary-empty {
				background: var(--vnt-surface);
				border: 1px dashed var(--vnt-border);
				border-radius: 10px;
				padding: 16px;
			}
			.vnt-bctc-summary-view .page-title {
				color: var(--vnt-text);
			}
			.vnt-bctc-summary-view .btn-default {
				border-radius: 999px;
				border: 1px solid var(--vnt-border);
				background: #fff;
				color: var(--vnt-text);
				padding: 6px 14px;
			}
			.vnt-bctc-summary-view .btn-default:hover {
				border-color: var(--vnt-accent);
				color: var(--vnt-accent);
			}
			.vnt-bctc-summary-view .control-input,
			.vnt-bctc-summary-view .form-control {
				border-radius: 10px;
			}
			.vnt-bctc-summary-view .control-input:focus,
			.vnt-bctc-summary-view .form-control:focus {
				border-color: var(--vnt-accent);
				box-shadow: 0 0 0 2px rgba(31, 111, 235, 0.15);
			}
		</style>
	`);
}

function download_excel(state) {
	if (!state.doc || !state.doc.name) {
		frappe.msgprint(__("Vui lòng chọn bảng tổng hợp trước."));
		return;
	}
	const method =
		state.doctype === "VNT Financial Actual Summary"
			? "vinatex.vnt_bctc.doctype.vnt_financial_actual_summary.vnt_financial_actual_summary.download_actual_summary_excel"
			: "vinatex.vnt_bctc.doctype.vnt_financial_plan_summary.vnt_financial_plan_summary.download_plan_summary_excel";
	const url = frappe.urllib.get_full_url(
		`/api/method/${method}?docname=${encodeURIComponent(state.doc.name)}`
	);
	window.open(url);
}

function import_excel(page, state) {
	if (!state.doc || !state.doc.name) {
		frappe.msgprint(__("Vui lòng chọn bảng tổng hợp trước."));
		return;
	}
	const method =
		state.doctype === "VNT Financial Actual Summary"
			? "vinatex.vnt_bctc.doctype.vnt_financial_actual_summary.vnt_financial_actual_summary.import_actual_summary_excel"
			: "vinatex.vnt_bctc.doctype.vnt_financial_plan_summary.vnt_financial_plan_summary.import_plan_summary_excel";
	new frappe.ui.FileUploader({
		doctype: state.doctype,
		docname: state.doc.name,
		restrictions: { allowed_file_types: [".xlsx", ".xls"] },
		on_success(file) {
			frappe.call({
				method,
				args: {
					docname: state.doc.name,
					file_url: file.file_url,
				},
				freeze: true,
				callback: () => load_doc(page, state),
			});
		},
	});
}

const NUMERIC_FIELDS = [
	"prev_plan",
	"prev_3t",
	"prev_6t",
	"prev_9t",
	"prev_12t",
	"current_plan",
	"current_3t",
	"current_6t",
	"current_9t",
	"current_12t",
	...Array.from({ length: 12 }, (_, i) => `prev_t${String(i + 1).padStart(2, "0")}`),
	...Array.from({ length: 12 }, (_, i) => `current_t${String(i + 1).padStart(2, "0")}`),
	"luy_ke",
];
const NUMBER_PRECISION = 6;

function bind_input_events(page, state) {
	$(page.main)
		.off("input.vnt-bctc", "input[data-row-idx]")
		.off("focus.vnt-bctc", "input[data-row-idx]")
		.off("blur.vnt-bctc", "input[data-row-idx]")
		.on("input.vnt-bctc", "input[data-row-idx]", (event) => {
			const idx = parseInt(event.currentTarget.dataset.rowIdx, 10);
			if (Number.isNaN(idx) || !state.doc || !state.doc.lines) {
				return;
			}
			const field = event.currentTarget.dataset.field;
			const raw = normalize_number(event.currentTarget.value);
			if (event.currentTarget.value !== raw) {
				event.currentTarget.value = raw;
			}
			state.doc.lines[idx][field] = raw === "" ? null : parse_number(raw);
		})
		.on("focus.vnt-bctc", "input[data-row-idx]", (event) => {
			const raw = normalize_number(event.currentTarget.value);
			event.currentTarget.value = raw;
		})
		.on("blur.vnt-bctc", "input[data-row-idx]", (event) => {
			const idx = parseInt(event.currentTarget.dataset.rowIdx, 10);
			if (Number.isNaN(idx) || !state.doc || !state.doc.lines) {
				return;
			}
			const field = event.currentTarget.dataset.field;
			const raw = normalize_number(event.currentTarget.value);
			state.doc.lines[idx][field] = raw === "" ? null : parse_number(raw);
			apply_ui_calculations(page, state, idx);
			event.currentTarget.value = raw ? format_number(raw) : "";
		});
}

function normalize_number(value) {
	const raw = String(value ?? "").trim();
	if (!raw) {
		return "";
	}
	let text = raw.replace(/\s+/g, "");
	text = text.replace(/[^\d,.\-]/g, "");
	if (!text || text === "-" || text === "." || text === ",") {
		return "";
	}
	let sign = "";
	if (text.startsWith("-")) {
		sign = "-";
		text = text.slice(1);
	}
	text = text.replace(/-/g, "");
	const hasDot = text.includes(".");
	const hasComma = text.includes(",");
	let decimalSep = null;
	if (hasDot && hasComma) {
		decimalSep = text.lastIndexOf(".") > text.lastIndexOf(",") ? "." : ",";
	} else if (hasComma) {
		const parts = text.split(",");
		decimalSep = parts.length > 1 && parts[parts.length - 1].length !== 3 ? "," : null;
	} else if (hasDot) {
		const parts = text.split(".");
		decimalSep = parts.length > 1 && parts[parts.length - 1].length !== 3 ? "." : null;
	}

	let normalized = "";
	if (decimalSep) {
		const parts = text.split(decimalSep);
		const intPart = parts[0].replace(/[.,]/g, "");
		const fracPart = parts
			.slice(1)
			.join("")
			.replace(/[.,]/g, "");
		normalized = intPart || "0";
		if (fracPart) {
			normalized += `.${fracPart}`;
		}
	} else {
		normalized = text.replace(/[.,]/g, "");
	}

	return normalized ? `${sign}${normalized}` : "";
}

function parse_number(value) {
	if (value === null || value === undefined) {
		return null;
	}
	const text = normalize_number(value);
	if (!text || text === "-") {
		return null;
	}
	const number = parseFloat(text);
	return Number.isNaN(number) ? null : number;
}

function apply_ui_calculations(page, state, row_idx) {
	const line = state.doc.lines[row_idx];
	if (!line) {
		return;
	}

	const quarter_updates = [
		...apply_quarter_months(line, "prev"),
		...apply_quarter_months(line, "current"),
	];
	if (quarter_updates.length) {
		update_row_inputs(page, state, row_idx, quarter_updates);
	}

	const profit_updates = apply_profit_for_group(state, line.doi_tuong);
	profit_updates.forEach((update) => {
		update_row_inputs(page, state, update.row_idx, update.fields);
	});
}

function apply_quarter_months(line, prefix) {
	const updates = [];
	const quarter_map = {
		3: `${prefix}_3t`,
		6: `${prefix}_6t`,
		9: `${prefix}_9t`,
		12: `${prefix}_12t`,
	};
	Object.keys(quarter_map).forEach((end_month) => {
		const month = parseInt(end_month, 10);
		const quarter_field = quarter_map[end_month];
		const quarter_value = normalize_snapshot_value(line[quarter_field]);
		if (quarter_value === null) {
			return;
		}
		const month_field = `${prefix}_t${String(month).padStart(2, "0")}`;
		if (line[month_field] !== null && line[month_field] !== undefined && line[month_field] !== "") {
			return;
		}
		let total = 0;
		for (let m = 1; m < month; m += 1) {
			const field = `${prefix}_t${String(m).padStart(2, "0")}`;
			const value = normalize_snapshot_value(line[field]);
			if (value !== null) {
				total += value;
			}
		}
		line[month_field] = quarter_value - total;
		updates.push(month_field);
	});
	return updates;
}

function apply_profit_for_group(state, group_name) {
	const updates = [];
	if (!group_name || !state.doc || !state.doc.lines) {
		return updates;
	}
	const group_key = normalize_text(group_name);
	if (!group_key) {
		return updates;
	}

	const totals = {
		doanh_thu: {},
		chi_phi: {},
	};

	state.doc.lines.forEach((line) => {
		if (normalize_text(line.doi_tuong) !== group_key) {
			return;
		}
		const kind = normalize_text(line.khoan_muc);
		if (kind !== "doanh thu" && kind !== "chi phi") {
			return;
		}
		const bucket = kind === "doanh thu" ? totals.doanh_thu : totals.chi_phi;
		NUMERIC_FIELDS.forEach((field) => {
			const value = normalize_snapshot_value(line[field]);
			if (value === null) {
				return;
			}
			bucket[field] = (bucket[field] || 0) + value;
		});
	});

	state.doc.lines.forEach((line, idx) => {
		if (normalize_text(line.doi_tuong) !== group_key) {
			return;
		}
		if (normalize_text(line.khoan_muc) !== "loi nhuan") {
			return;
		}
		const updated_fields = [];
		NUMERIC_FIELDS.forEach((field) => {
			const revenue = totals.doanh_thu[field];
			const cost = totals.chi_phi[field];
			if (revenue === undefined && cost === undefined) {
				return;
			}
			line[field] = (revenue || 0) - (cost || 0);
			updated_fields.push(field);
		});
		if (updated_fields.length) {
			updates.push({ row_idx: idx, fields: updated_fields });
		}
	});

	return updates;
}

function update_row_inputs(page, state, row_idx, fields) {
	const $root = $(page.main);
	fields.forEach((field) => {
		const $input = $root.find(`input[data-row-idx="${row_idx}"][data-field="${field}"]`);
		if ($input.length) {
			$input.val(format_number(state.doc.lines[row_idx][field]));
		}
	});
}

function normalize_text(value) {
	const text = (value || "").toString().trim().toLowerCase();
	return text
		.normalize("NFD")
		.replace(/[\u0300-\u036f]/g, "")
		.replace(/\s+/g, " ");
}


function save_doc(page, state) {
	if (!state.doc || !state.doc.name) {
		frappe.msgprint(__("Vui lòng chọn bảng tổng hợp trước."));
		return;
	}
	const method =
		state.doctype === "VNT Financial Actual Summary"
			? "vinatex.vnt_bctc.doctype.vnt_financial_actual_summary.vnt_financial_actual_summary.save_actual_summary_lines"
			: "vinatex.vnt_bctc.doctype.vnt_financial_plan_summary.vnt_financial_plan_summary.save_plan_summary_lines";
	if (!has_changes(state)) {
		frappe.msgprint(__("Không có thay đổi để lưu."));
		return;
	}

	const payload = (state.doc.lines || []).map((line) => {
		const row = { name: line.name };
		NUMERIC_FIELDS.forEach((field) => {
			row[field] = line[field];
		});
		return row;
	});
	frappe.call({
		method,
		args: {
			docname: state.doc.name,
			lines: payload,
		},
		freeze: true,
		callback: (r) => {
			if (r && r.exc) {
				frappe.msgprint(__("Lưu thất bại. Vui lòng thử lại."));
				return;
			}
			frappe.msgprint(__("Lưu thành công."));
			load_doc(page, state);
		},
		error: () => {
			frappe.msgprint(__("Lưu thất bại. Vui lòng thử lại."));
		},
	});
}

function snapshot_lines(lines) {
	const snapshot = {};
	lines.forEach((line) => {
		if (!line.name) {
			return;
		}
		const values = {};
		NUMERIC_FIELDS.forEach((field) => {
			values[field] = normalize_snapshot_value(line[field]);
		});
		snapshot[line.name] = values;
	});
	return snapshot;
}

function normalize_snapshot_value(value) {
	if (value === null || value === undefined || value === "") {
		return null;
	}
	const number = Number(value);
	return Number.isNaN(number) ? null : number;
}

function has_changes(state) {
	const original = state.original_lines || {};
	const current = state.doc ? state.doc.lines || [] : [];
	for (const line of current) {
		const row_name = line.name;
		if (!row_name || !original[row_name]) {
			return true;
		}
		for (const field of NUMERIC_FIELDS) {
			const before = original[row_name][field];
			const now = normalize_snapshot_value(line[field]);
			if (before !== now) {
				return true;
			}
		}
	}
	return false;
}
