frappe.pages["vnt-financial-plan-book-grouped"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Kế hoạch BCTC"),
		single_column: true,
	});

	const state = {
		doc: null,
		groups: [],
		rows: [],
		controls: {},
	};

	page.set_primary_action(__("Lưu"), () => save_book(page, state));

	$(page.main).html(`
		<div class="vnt-bctc-entry">
			<div class="vnt-bctc-filters"></div>
			<div class="vnt-bctc-entry-meta text-muted"></div>
			<div class="vnt-bctc-entry-body"></div>
		</div>
	`);

	render_filters(page, state);
	inject_styles(page);
	set_empty_state(page);
	set_default_book(page, state);
};

function render_filters(page, state) {
	const $filters = $(page.main).find(".vnt-bctc-filters");
	const book_control = frappe.ui.form.make_control({
		df: {
			fieldname: "book",
			label: __("Sổ kế hoạch"),
			fieldtype: "Link",
			options: "VNT Financial Plan Book",
			reqd: 1,
			change() {
				load_book(page, state);
			},
		},
		parent: $filters,
		render_input: true,
	});

	book_control.make();
	book_control.$input.on("change", () => load_book(page, state));
	state.controls.book = book_control;

	const $actions = $(`
		<div class="vnt-bctc-filter-actions">
			<button class="btn btn-primary btn-sm vnt-bctc-create" type="button">${__(
				"Tạo kế hoạch mới"
			)}</button>
		</div>
	`);
	$filters.append($actions);
	$actions.find(".vnt-bctc-create").on("click", () => open_create_dialog(page, state));
}

function load_book(page, state) {
	const control = state.controls.book;
	const docname = control ? control.get_value() : null;
	if (!docname) {
		state.doc = null;
		state.groups = [];
		state.rows = [];
		set_empty_state(page);
		return;
	}

	frappe.call({
		method:
			"vinatex.vnt_bctc.doctype.vnt_financial_plan_book.vnt_financial_plan_book.get_grouped_plan_book_data",
		args: { docname },
		freeze: true,
		callback: (r) => {
			if (!r || !r.message) {
				return;
			}
			state.doc = r.message.doc;
			state.groups = r.message.groups || [];
			render_groups(page, state);
		},
	});
}

function render_groups(page, state) {
	const $main = $(page.main);
	const $meta = $main.find(".vnt-bctc-entry-meta");
	const $body = $main.find(".vnt-bctc-entry-body");

	if (!state.doc) {
		set_empty_state(page);
		return;
	}

	$meta.html(`
		<div><strong>${escape_html(state.doc.name)}</strong></div>
		<div>Công ty: ${escape_html(state.doc.company || "-")}</div>
		<div>Năm tài chính: ${escape_html(state.doc.fiscal_year || "-")}</div>
		
	`);

	state.rows = [];
	let html = "";

	(state.groups || []).forEach((group) => {
		const group_label = escape_html(group.label || "");
		const item_groups = new Map();
		const item_order = [];
		(group.items || []).forEach((item) => {
			const key = (item.doi_tuong || "").trim() || __("Khác");
			if (!item_groups.has(key)) {
				item_groups.set(key, []);
				item_order.push(key);
			}
			item_groups.get(key).push(item);
		});

		let group_html = "";
		item_order.forEach((object_name) => {
			const items = item_groups.get(object_name) || [];
			let rows_html = "";
			items.forEach((item) => {
				const row_idx = state.rows.length;
				state.rows.push({
					doi_tuong: item.doi_tuong || "",
					ct_doi_tuong: item.ct_doi_tuong || "",
					chi_tiet_doi_tuong_c2: item.chi_tiet_doi_tuong_c2 || "",
					khoan_muc: item.khoan_muc || "",
					ct: item.ct || "",
					annual_plan_value: item.annual_plan_value,
					plan_3t: item.plan_3t,
					plan_6t: item.plan_6t,
					plan_9t: item.plan_9t,
					plan_12t: item.plan_12t,
				});

				rows_html += `
					<tr>
						<td>${escape_html(item.ct_doi_tuong || "")}</td>
						<td>${escape_html(item.chi_tiet_doi_tuong_c2 || "")}</td>
						<td>${escape_html(item.khoan_muc || "")}</td>
						<td>${escape_html(item.ct || "")}</td>
						<td><input type="text" class="form-control input-xs text-right" data-field="annual_plan_value" data-row-idx="${row_idx}" value="${format_number(item.annual_plan_value)}" /></td>
						<td><input type="text" class="form-control input-xs text-right" data-field="plan_3t" data-row-idx="${row_idx}" value="${format_number(item.plan_3t)}" /></td>
						<td><input type="text" class="form-control input-xs text-right" data-field="plan_6t" data-row-idx="${row_idx}" value="${format_number(item.plan_6t)}" /></td>
						<td><input type="text" class="form-control input-xs text-right" data-field="plan_9t" data-row-idx="${row_idx}" value="${format_number(item.plan_9t)}" /></td>
						<td><input type="text" class="form-control input-xs text-right" data-field="plan_12t" data-row-idx="${row_idx}" value="${format_number(item.plan_12t)}" /></td>
					</tr>
				`;
			});

			if (!rows_html) {
				rows_html = `
					<tr>
						<td colspan="9" class="text-muted">Không có dữ liệu</td>
					</tr>
				`;
			}

			group_html += `
				<div class="vnt-bctc-object">
					<div class="vnt-bctc-object-title">${escape_html(object_name)}</div>
					<div class="table-responsive">
						<table class="table table-bordered table-hover">
							<thead>
								<tr>
									<th>Chi tiết đối tượng</th>
									<th>Chi tiết đối tượng cấp 2</th>
									<th>Khoản mục</th>
									<th>Chi tiết khoản mục</th>
									<th>KH năm</th>
									<th>3T</th>
									<th>6T</th>
									<th>9T</th>
									<th>12T</th>
								</tr>
							</thead>
							<tbody>
								${rows_html}
							</tbody>
						</table>
					</div>
				</div>
			`;
		});

		html += `
			<div class="vnt-bctc-group">
				<div class="h6">${group_label}</div>
				${group_html || `<div class="text-muted">Không có dữ liệu</div>`}
			</div>
		`;
	});

	$body.html(html || `<div class="text-muted">Không có nhóm dữ liệu.</div>`);
	bind_input_events(page, state);
}

function bind_input_events(page, state) {
	$(page.main)
		.off("input.vnt-bctc", "input[data-row-idx]")
		.off("focus.vnt-bctc", "input[data-row-idx]")
		.off("blur.vnt-bctc", "input[data-row-idx]")
		.on("input.vnt-bctc", "input[data-row-idx]", (event) => {
			const idx = parseInt(event.currentTarget.dataset.rowIdx, 10);
			if (Number.isNaN(idx)) {
				return;
			}
			const field = event.currentTarget.dataset.field;
			const raw = normalize_integer(event.currentTarget.value);
			if (event.currentTarget.value !== raw) {
				event.currentTarget.value = raw;
			}
			state.rows[idx][field] = raw === "" ? null : parse_number(raw);
		})
		.on("focus.vnt-bctc", "input[data-row-idx]", (event) => {
			const raw = normalize_integer(event.currentTarget.value);
			event.currentTarget.value = raw;
		})
		.on("blur.vnt-bctc", "input[data-row-idx]", (event) => {
			const raw = normalize_integer(event.currentTarget.value);
			event.currentTarget.value = raw ? format_number(raw) : "";
		});
}

function save_book(page, state) {
	if (!state.doc) {
		frappe.msgprint(__("Vui lòng chọn sổ kế hoạch trước khi lưu."));
		return;
	}

	sync_values_from_dom(page, state);

	frappe.call({
		method:
			"vinatex.vnt_bctc.doctype.vnt_financial_plan_book.vnt_financial_plan_book.save_grouped_plan_book",
		args: {
			docname: state.doc.name,
			lines: state.rows,
		},
		freeze: true,
		callback: (r) => {
			if (r && r.message) {
				frappe.show_alert({ message: __("Đã lưu dữ liệu."), indicator: "green" });
			}
		},
	});
}

function sync_values_from_dom(page, state) {
	$(page.main)
		.find("input[data-row-idx]")
		.each((_, input) => {
			const idx = parseInt(input.dataset.rowIdx, 10);
			if (Number.isNaN(idx)) {
				return;
			}
			const field = input.dataset.field;
			const raw = normalize_integer(input.value);
			state.rows[idx][field] = raw === "" ? null : parse_number(raw);
		});
}

function set_empty_state(page) {
	const $main = $(page.main);
	$main.find(".vnt-bctc-entry-meta").text(__("Chọn sổ kế hoạch để nhập liệu."));
	$main.find(".vnt-bctc-entry-body").empty();
}

function set_default_book(page, state) {
	const control = state.controls.book;
	if (!control || control.get_value()) {
		return;
	}
	frappe.db
		.get_list("VNT Financial Plan Book", {
			fields: ["name", "modified"],
			order_by: "modified desc",
			limit: 1,
		})
		.then((rows) => {
			if (!rows || !rows.length || control.get_value()) {
				return;
			}
			control.set_value(rows[0].name);
			load_book(page, state);
		});
}

function open_create_dialog(page, state) {
	const dialog = new frappe.ui.Dialog({
		title: __("Tạo sổ kế hoạch mới"),
		fields: [
			{
				fieldname: "company",
				label: __("Công ty"),
				fieldtype: "Link",
				options: "Company",
				reqd: 1,
			},
			{
				fieldname: "fiscal_year",
				label: __("Năm tài chính"),
				fieldtype: "Link",
				options: "Fiscal Year",
				reqd: 1,
			},
			{
				fieldname: "template",
				label: __("Mẫu báo cáo"),
				fieldtype: "Link",
				options: "VNT Financial Report Template",
				reqd: 1,
			},
			// {
			// 	fieldname: "scenario",
			// 	label: __("Kịch bản"),
			// 	fieldtype: "Select",
			// 	options: ["Kế hoạch", "Dự báo", "Ngân sách"].join("\n"),
			// 	default: "Kế hoạch",
			// },
			{
				fieldname: "version_no",
				label: __("Phiên bản"),
				fieldtype: "Data",
			},
		],
		primary_action_label: __("Tạo kế hoạch"),
		primary_action(values) {
			frappe.call({
				method:
					"vinatex.vnt_bctc.doctype.vnt_financial_plan_book.vnt_financial_plan_book.create_plan_book",
				args: values,
				freeze: true,
				callback: (r) => {
					if (r && r.message) {
						dialog.hide();
						if (state.controls.book) {
							state.controls.book.set_value(r.message.name);
						}
						load_book(page, state);
					}
				},
			});
		},
	});

	dialog.show();
	set_dialog_defaults(dialog);
}

function set_dialog_defaults(dialog) {
	const company_default = frappe.defaults.get_default("company");
	if (company_default) {
		dialog.set_value("company", company_default);
	}

	get_default_fiscal_year().then((fy) => {
		if (fy && !dialog.get_value("fiscal_year")) {
			dialog.set_value("fiscal_year", fy);
		}
	});

	get_default_template().then((template) => {
		if (template && !dialog.get_value("template")) {
			dialog.set_value("template", template);
		}
	});
}

function inject_styles(page) {
	if (page._vnt_bctc_styles) {
		return;
	}
	page._vnt_bctc_styles = true;
	$(page.main).append(`
		<style>
			.vnt-bctc-entry {
				display: flex;
				flex-direction: column;
				gap: 16px;
			}
			.vnt-bctc-filters {
				display: flex;
				align-items: center;
				gap: 12px;
				flex-wrap: wrap;
			}
			.vnt-bctc-filter-actions {
				display: flex;
				gap: 8px;
			}
			.vnt-bctc-entry-meta {
				background: #f8fafc;
				border: 1px solid #e5e7eb;
				border-radius: 8px;
				padding: 12px 16px;
				display: grid;
				grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
				gap: 4px 16px;
			}
			.vnt-bctc-group {
				background: #ffffff;
				border: 1px solid #e5e7eb;
				border-radius: 10px;
				padding: 12px 12px 4px;
				box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
				margin-bottom: 16px;
			}
			.vnt-bctc-group .h6 {
				font-weight: 600;
				font-size: 20px;
				margin-bottom: 12px;
			}
			.vnt-bctc-object {
				margin-bottom: 16px;
			}
			.vnt-bctc-object-title {
				font-weight: 600;
				color: #1f2937;
				margin-bottom: 8px;
			}
			.vnt-bctc-group table {
				margin-bottom: 8px;
			}
			.vnt-bctc-group thead th {
				background: #f1f5f9;
				position: sticky;
				top: 0;
				z-index: 1;
				white-space: nowrap;
			}
			.vnt-bctc-group tbody tr:hover {
				background: #f8fafc;
			}
			.vnt-bctc-group td {
				vertical-align: middle;
			}
			.vnt-bctc-group input.form-control {
				min-width: 110px;
			}
		</style>
	`);
}

function parse_number(value) {
	if (value === null || value === undefined) {
		return null;
	}
	const text = normalize_integer(value);
	if (!text) {
		return null;
	}
	const number = parseFloat(text);
	return Number.isNaN(number) ? null : number;
}

function format_number(value) {
	if (value === null || value === undefined || value === "") {
		return "";
	}
	const text = normalize_integer(value);
	if (!text) {
		return "";
	}
	const number = parseFloat(text);
	if (Number.isNaN(number)) {
		return "";
	}
	if (typeof frappe.format_number === "function") {
		return frappe.format_number(number, null, 0);
	}
	return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(number);
}

function escape_html(value) {
	return frappe.utils.escape_html(value || "");
}

function normalize_integer(value) {
	const text = String(value || "").replace(/[^\d-]/g, "");
	if (!text || text === "-") {
		return "";
	}
	const sign = text.startsWith("-") ? "-" : "";
	const digits = text.replace(/-/g, "");
	return sign + digits;
}

function get_default_fiscal_year() {
	const today = frappe.datetime.nowdate();
	return frappe.db
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
			if (rows && rows.length) {
				return rows[0].name;
			}
			return frappe.db
				.get_list("Fiscal Year", {
					fields: ["name", "year_start_date"],
					order_by: "year_start_date desc",
					limit: 1,
				})
				.then((fallback) => (fallback && fallback.length ? fallback[0].name : null));
		});
}

function get_default_template() {
	return frappe.db
		.get_list("VNT Financial Report Template", {
			filters: { is_active: 1 },
			fields: ["name"],
			order_by: "creation desc",
			limit: 1,
		})
		.then((rows) => (rows && rows.length ? rows[0].name : null));
}
