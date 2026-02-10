// Copyright (c) 2026, vinatex and contributors
// For license information, please see license.txt

const load_kpi_ban_items = (frm) => {
	const kpiYear = frm.doc.kpi_year;
	const department = frm.doc.department;
	const type = frm.doc.type;

	if (!kpiYear || !department || !type || type === "Điều chỉnh") {
		return;
	}

	const fetchItems = () => {
		frappe.call({
			method: "vinatex.vnt_hr.doctype.vnt_kpi_ban.vnt_kpi_ban.get_effective_kpi_ban_doc",
			args: {
				kpi_year: kpiYear,
				department: department,
				business_type: type,
			},
			freeze: true,
			freeze_message: __("Loading KPI Ban..."),
		}).then((r) => {
			const payload = r.message || {};
			const items = payload.items || [];
			if (!items.length) {
				frappe.msgprint(
					__("Không tìm thấy công việc nào năm {0} cho Ban {1}.", [
						kpiYear,
						department,
					])
				);
				return;
			}

			frm.clear_table("items");
			items.forEach((item) => {
				const row = frm.add_child("items");
				row.kpi_details = item.kpi_details;
				row.kpi_ban_item = item.name;
				row.percent = item.percent;
				row.date = item.date;
				row.note = item.note;
			});

			frm.refresh_field("items");
		});
	};

	if (frm.doc.items && frm.doc.items.length) {
		frappe.confirm(
			__("Bạn có muốn lấy dữ liệu KPI của Phòng/Ban tự động?"),
			() => fetchItems(),
			() => {}
		);
	} else {
		fetchItems();
	}
};

const openTaskDialog = (frm) => {
	if (!frm.doc.items || !frm.doc.items.length) {
		frappe.msgprint(__("Bạn cần có KPI chuyên viên trước khi tạo task."));
		return;
	}

	const kpiItemOptions = (frm.doc.items || []).map((row) => {
		const deadline = row.date ? frappe.datetime.str_to_user(row.date) : __("Chưa đặt");
		const percent = row.percent || 0;
		return {
			name: row.name,
			label: `${row.idx}. ${row.kpi_details || __("Chưa có mô tả")} | ${percent}% | ${__(
				"Hạn"
			)}: ${deadline}`,
			kpi_details: row.kpi_details,
			percent: percent,
			deadline: deadline,
		};
	});

	const escapeHtml = (value) =>
		String(value || "")
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");

	const renderSelectedItemInfo = (dialog) => {
		const selectedLabel = dialog.get_value("kpi_cv_item_label");
		const selected = kpiItemOptions.find((opt) => opt.label === selectedLabel);
		const html = selected
			? `<div style="padding: 8px 0; color: var(--text-muted);">
				<b>${escapeHtml(selected.kpi_details)}</b><br>
				% KPI: ${selected.percent} | ${__("Hạn")}: ${selected.deadline}
			</div>`
			: `<div style="padding: 8px 0; color: var(--text-muted);">
				${__("Chọn KPI chuyên viên để xem thông tin chi tiết.")}
			</div>`;
		dialog.fields_dict.kpi_cv_item_info.$wrapper.html(html);
	};

	const renderTaskSummary = (dialog, payload) => {
		const cap = payload.allocation_cap_percent || 100;
		const monthSummaries = payload.month_summaries || [];
		const itemPercent = payload.item_percent || 0;

		if (!monthSummaries.length) {
			dialog.fields_dict.tasks_summary.$wrapper.html(
				`<div style="padding: 4px 0; color: var(--text-muted);">
					${__("Chưa có phân bổ theo tháng")} | ${__("KPI có tỉ trọng")}: ${itemPercent}%
				</div>`
			);
			return;
		}

		const summaryLines = monthSummaries
			.map(
				(row) =>
					`${__("Tháng")} ${row.month_label}: ${row.allocated_percent || 0}% / ${cap}% | ${__(
						"Còn lại"
					)}: ${row.remaining_percent || 0}%`
			)
			.join("<br>");

		dialog.fields_dict.tasks_summary.$wrapper.html(
			`<div style="padding: 4px 0; color: var(--text-muted);">
				${summaryLines}<br>
				${__("KPI có tỉ trọng")}: ${itemPercent}%
			</div>`
		);
	};

	const setTaskRows = (dialog, rows) => {
		const tableField = dialog.fields_dict.tasks;
		if (!tableField || !tableField.grid) {
			return;
		}
		const defaultType = dialog.get_value("default_type") || null;
		tableField.df.data = (rows || []).map((rowData, index) => ({
			idx: index + 1,
			__islocal: true,
			loai: rowData.loai || defaultType,
			...rowData,
		}));
		tableField.grid.refresh();
	};

	const loadExistingTasks = (dialog) => {
		const selectedLabel = dialog.get_value("kpi_cv_item_label");
		const selected = kpiItemOptions.find((opt) => opt.label === selectedLabel);
		if (!selected) {
			setTaskRows(dialog, []);
			dialog.fields_dict.tasks_summary.$wrapper.empty();
			return;
		}

			frappe.call({
				method: "vinatex.vnt_hr.doctype.vnt_kpi_chuyen_vien.vnt_kpi_chuyen_vien.get_tasks_for_kpi_chuyen_vien_item",
			args: {
				kpi_chuyen_vien: frm.doc.name,
				kpi_cv_item: selected.name,
			},
				freeze: true,
				freeze_message: __("Đang tải task đã tạo..."),
			}).then((r) => {
				const payload = r.message || {};
				dialog.set_value("default_type", payload.default_type || frm.doc.type);
				const taskRows = (payload.items || []).map((row) => ({
					task_name: row.task_name,
					congviec: row.congviec,
					loai: row.loai || payload.default_type,
					percent: row.percent,
					deadline: row.deadline,
					exp_start_date: row.exp_start_date,
					expected_time: row.expected_time,
					details: row.details,
				}));

				setTaskRows(dialog, taskRows);
				renderSelectedItemInfo(dialog);
				renderTaskSummary(dialog, payload);
			});
		};

	const dialog = new frappe.ui.Dialog({
		title: __("Tạo công việc chi tiết"),
		size: "large",
			fields: [
				{
					fieldname: "default_type",
					fieldtype: "Data",
					hidden: 1,
				},
				{
					fieldname: "kpi_cv_item_label",
					fieldtype: "Select",
				label: __("KPI Chuyên viên"),
				options: ["", ...kpiItemOptions.map((opt) => opt.label)].join("\n"),
				default: kpiItemOptions[0] ? kpiItemOptions[0].label : "",
				reqd: 1,
			},
			{
				fieldname: "kpi_cv_item_info",
				fieldtype: "HTML",
			},
			{
				fieldname: "tasks",
				fieldtype: "Table",
				label: __("Danh sách task"),
				reqd: 0,
				in_place_edit: true,
				fields: [
					{
						fieldname: "task_name",
						fieldtype: "Data",
						hidden: 1,
					},
					{
						fieldname: "congviec",
						fieldtype: "Data",
						label: __("Tên công việc"),
						reqd: 1,
						in_list_view: 1,
					},
					{
						fieldname: "loai",
						fieldtype: "Select",
						label: __("Loại"),
						options: "\nTheo kế hoạch\nĐiều chỉnh\nPhát sinh\nNội bộ",
						default: frm.doc.type || "",
						in_list_view: 1,
					},
					{
						fieldname: "percent",
						fieldtype: "Percent",
						label: __("% công việc"),
						reqd: 1,
						in_list_view: 1,
					},
					{
						fieldname: "exp_start_date",
						fieldtype: "Date",
						label: __("Ngày bắt đầu"),
						reqd: 1,
						in_list_view: 1,
					},
					{
						fieldname: "expected_time",
						fieldtype: "Float",
						label: __("Giờ dự kiến"),
					},
					{
						fieldname: "deadline",
						fieldtype: "Date",
						label: __("Thời hạn"),
						reqd: 1,
						in_list_view: 1,
					},
					{
						fieldname: "details",
						fieldtype: "Small Text",
						label: __("Chi tiết"),
					},
				],
			},
			{
				fieldname: "tasks_summary",
				fieldtype: "HTML",
			},
		],
		primary_action_label: __("Tạo Task"),
		primary_action(values) {
			const selected = kpiItemOptions.find(
				(opt) => opt.label === values.kpi_cv_item_label
			);
			if (!selected) {
				frappe.msgprint(
					__("KPI Chuyên viên đã chọn không thuộc chứng từ hiện tại.")
				);
				return;
			}

			if (!values.tasks || !values.tasks.length) {
				frappe.msgprint(__("Vui lòng nhập ít nhất 1 task."));
				return;
			}

			const invalidDateRows = [];
			(values.tasks || []).forEach((row, idx) => {
				const start = row.exp_start_date
					? frappe.datetime.str_to_obj(row.exp_start_date)
					: null;
				const end = row.deadline ? frappe.datetime.str_to_obj(row.deadline) : null;
				if (!start || !end) {
					invalidDateRows.push(idx + 1);
					return;
				}
				if (
					start.getFullYear() !== end.getFullYear() ||
					start.getMonth() !== end.getMonth() ||
					start > end
				) {
					invalidDateRows.push(idx + 1);
				}
			});

			if (invalidDateRows.length) {
				frappe.msgprint(
					__(
						"Dòng {0}: Ngày bắt đầu và Thời hạn phải trong cùng một tháng.",
						[invalidDateRows.join(", ")]
					)
				);
				return;
			}

				frappe.call({
					method: "vinatex.vnt_hr.doctype.vnt_kpi_chuyen_vien.vnt_kpi_chuyen_vien.create_tasks_from_kpi_chuyen_vien",
				args: {
					kpi_chuyen_vien: frm.doc.name,
					kpi_cv_item: selected.name,
					entries: values.tasks || [],
				},
				freeze: true,
				freeze_message: __("Đang tạo task..."),
			}).then((r) => {
					const payload = r.message || {};
					const created = payload.created_tasks || [];
					const updated = payload.updated_tasks || [];
					const monthSummaries = payload.month_summaries || [];

					if (created.length || updated.length) {
						const monthInfo = monthSummaries.length
							? `${__("Số tháng cập nhật")}: ${monthSummaries.length}.`
							: "";
						frappe.show_alert({
							message: __(
								"Đã tạo {0}, cập nhật {1} task. {2}",
								[
									created.length,
									updated.length,
									monthInfo,
								]
							),
						indicator: "green",
					});
				}

				dialog.hide();
			});
		},
	});

	dialog.show();
	dialog.$wrapper.find(".modal-dialog").css("max-width", "1260px");
	dialog.$wrapper
		.find(".grid-body")
		.css({ "max-height": "360px", "overflow-y": "auto" });
	dialog.fields_dict.kpi_cv_item_label.df.onchange = () => {
		loadExistingTasks(dialog);
	};
	dialog.fields_dict.kpi_cv_item_label.refresh();
	loadExistingTasks(dialog);
};

frappe.ui.form.on("VNT KPI Chuyen Vien", {
	kpi_year(frm) {
		load_kpi_ban_items(frm);
	},
	department(frm) {
		load_kpi_ban_items(frm);
	},
	type(frm) {
		load_kpi_ban_items(frm);
	},
	refresh(frm) {
		if (!frm.doc.employee) {
			frappe.db
				.get_value("Employee", { user_id: frappe.session.user }, "name")
				.then((r) => {
					if (r.message) {
						frm.set_value("employee", r.message.name);
					}
				});
		}

		if (!frm.doc.date) {
			frm.set_value("date", frappe.datetime.get_today());
		}

		if (!frm.doc.kpi_year) {
			frm.set_value("kpi_year", frappe.datetime.get_today().substr(0, 4));
		}

		if (!frm.is_new() && frm.doc.docstatus < 2) {
			frm.add_custom_button(__("Tạo Task Chi Tiết"), () => openTaskDialog(frm));
		}
	},
});
