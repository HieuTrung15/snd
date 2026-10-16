// Bulk Kíp transfer action for the standard Employee list.

(() => {
	const existing = frappe.listview_settings.Employee || {};
	const original_onload = existing.onload;

	frappe.listview_settings.Employee = Object.assign({}, existing, {
		onload(listview) {
			if (original_onload) original_onload(listview);
			if (!(
				frappe.user.has_role("HR User") ||
				frappe.user.has_role("HR Manager") ||
				frappe.user.has_role("System Manager")
			))
				return;

			listview.page.add_actions_menu_item(__("Phân / chuyển kíp hàng loạt"), () => {
				const employees = listview.get_checked_items().map((row) => row.name);
				if (!employees.length) {
					frappe.msgprint(__("Hãy chọn ít nhất một nhân sự."));
					return;
				}
				open_transfer_dialog(employees);
			});

			if (!frappe._vnt_shift_group_transfer_listener) {
				frappe._vnt_shift_group_transfer_listener = true;
				frappe.realtime.on("vnt_bulk_shift_group_transfer_completed", (result) => {
					show_result(result);
					listview.refresh();
				});
			}
		},
	});

	function open_transfer_dialog(employees) {
		const dialog = new frappe.ui.Dialog({
			title: __("Phân / chuyển kíp hàng loạt ({0} nhân sự)", [employees.length]),
			fields: [
				{
					fieldname: "target_shift_group",
					fieldtype: "Link",
					options: "VNT Shift Group",
					label: __("Kíp mới"),
					reqd: 1,
					get_query: () => ({ filters: { disabled: 0 } }),
					onchange: () => set_group_period_defaults(dialog),
				},
				{
					fieldname: "effective_date",
					fieldtype: "Date",
					label: __("Ngày hiệu lực"),
					default: frappe.datetime.get_today(),
					reqd: 1,
					onchange: () => keepGenerateUntilInsideMembership(dialog),
				},
				{ fieldname: "column_break_dates", fieldtype: "Column Break" },
				{
					fieldname: "membership_end_date",
					fieldtype: "Date",
					label: __("Ngày kết thúc thuộc kíp"),
					reqd: 1,
					onchange: () => keepGenerateUntilInsideMembership(dialog),
				},
				{
					fieldname: "generate_until",
					fieldtype: "Date",
					label: __("Tạo ca kế hoạch đến ngày"),
					reqd: 1,
					hidden: 1,
					onchange: () => keepGenerateUntilInsideMembership(dialog),
				},
				{
					fieldname: "note",
					fieldtype: "Small Text",
					label: __("Lý do / Ghi chú"),
					reqd: 1,
				},
			],
			primary_action_label: __("Xem trước"),
			primary_action(values) {
				if (!validateTransferPeriod(values)) return;
				frappe.call({
					method: "vinatex.vnt_hr.shift_management.shift_group_transfer_service.preview_bulk_shift_group_transfer",
					args: { ...values, employees },
					freeze: true,
					freeze_message: __("Đang kiểm tra kíp và ca kế hoạch tương lai..."),
					callback: (r) => {
						const preview = r.message;
						show_preview(
							preview,
							(preview.counts.BLOCKED || 0) > 0
								? null
								: () => execute_transfer(values, employees, dialog),
						);
					},
				});
			},
		});
		dialog.show();
	}

	function set_group_period_defaults(dialog) {
		const shift_group = dialog.get_value("target_shift_group");
		if (!shift_group) return;
		frappe.db
			.get_value("VNT Shift Group", shift_group, ["effective_from", "effective_to"])
			.then((r) => {
				const period = r.message || {};
				if (
					period.effective_from &&
					dialog.get_value("effective_date") < period.effective_from
				)
					dialog.set_value("effective_date", period.effective_from);
				if (period.effective_to) {
					dialog.set_value("membership_end_date", period.effective_to);
					dialog.set_value("generate_until", period.effective_to);
				}
			});
	}

	function keepGenerateUntilInsideMembership(dialog) {
		const effectiveDate = dialog.get_value("effective_date");
		const membershipEndDate = dialog.get_value("membership_end_date");
		const generateUntil = dialog.get_value("generate_until");
		if (!generateUntil) return;

		let adjustedDate = generateUntil;
		if (effectiveDate && adjustedDate < effectiveDate) adjustedDate = effectiveDate;
		if (membershipEndDate && adjustedDate > membershipEndDate)
			adjustedDate = membershipEndDate;
		if (adjustedDate !== generateUntil) {
			dialog.set_value("generate_until", adjustedDate);
			frappe.show_alert({
				message: __("Ngày tạo ca đã được điều chỉnh để nằm trong khoảng thuộc kíp."),
				indicator: "orange",
			});
		}
	}

	function validateTransferPeriod(values) {
		if (values.effective_date > values.membership_end_date) {
			frappe.msgprint(__("Ngày hiệu lực không được sau ngày kết thúc thuộc kíp."));
			return false;
		}
		if (
			values.generate_until < values.effective_date ||
			values.generate_until > values.membership_end_date
		) {
			frappe.msgprint(__("Ngày tạo ca phải nằm trong khoảng thuộc kíp."));
			return false;
		}
		return true;
	}

	function execute_transfer(values, employees, dialog) {
		dialog.hide();
		frappe.call({
			method: "vinatex.vnt_hr.shift_management.shift_group_transfer_service.execute_bulk_shift_group_transfer",
			args: { ...values, employees },
			freeze: true,
			freeze_message: __("Đang thực hiện phân / chuyển kíp hàng loạt..."),
			callback: (r) => show_result(r.message),
		});
	}

	function show_preview(preview, onConfirm) {
		const actionLabels = {
			CREATE_MEMBERSHIP: __("Tạo thông tin thuộc kíp mới"),
			KEEP_MEMBERSHIP: __("Giữ thông tin kíp đích hiện có"),
			EXTEND_MEMBERSHIP: __("Gia hạn thông tin kíp đích"),
			CLOSE_AND_CREATE: __("Kết thúc kíp cũ và tạo kíp mới"),
			INACTIVATE_AND_CREATE: __(
				"Ngừng thông tin kíp cùng ngày và tạo kíp mới",
			),
		};
		const rows = preview.rows.slice(0, 100).map((row) => {
			const detail = row.blockers.length
				? row.blockers.join("; ")
				: actionLabels[row.membership_action] || row.membership_action;
			return `<tr>
			<td>${frappe.utils.escape_html(row.employee)}</td>
			<td>${frappe.utils.escape_html(row.employee_name || "")}</td>
			<td>${frappe.utils.escape_html(row.current_shift_group || "-")}</td>
			<td>${frappe.utils.escape_html(row.target_shift_group)}</td>
			<td>${row.auto_assignments_to_cancel}</td>
			<td class="${row.status === "BLOCKED" ? "text-danger" : "text-success"}">${frappe.utils.escape_html(row.status === "BLOCKED" ? __("Bị chặn") : __("Sẵn sàng"))}</td>
			<td>${frappe.utils.escape_html(detail)}</td>
		</tr>`;
		});
		const truncated =
			preview.rows.length > 100 ? `<p>${__("Chỉ hiển thị 100 dòng đầu tiên.")}</p>` : "";
		const message = `
			<p>${__("Sẵn sàng")}: ${preview.counts.READY || 0} &nbsp; ${__("Bị chặn")}: ${preview.counts.BLOCKED || 0}</p>
			<p>${__("Số ca tự động sẽ hủy")}: ${preview.auto_assignments_to_cancel} &nbsp; ${__("Số ca thủ công được giữ nguyên")}: ${preview.manual_assignments_preserved}</p>
			${truncated}
			<div class="table-responsive"><table class="table table-bordered table-sm">
				<thead><tr><th>${__("Mã nhân viên")}</th><th>${__("Tên nhân viên")}</th><th>${__("Kíp hiện tại")}</th><th>${__("Kíp mới")}</th><th>${__("Số ca hủy")}</th><th>${__("Trạng thái")}</th><th>${__("Chi tiết")}</th></tr></thead>
				<tbody>${rows.join("")}</tbody>
			</table></div>`;
		const options = {
			title: __("Xem trước phân / chuyển kíp hàng loạt"),
			wide: true,
			message,
		};
		if (onConfirm) {
			options.primary_action = {
				label: __("Xác nhận chuyển kíp"),
				action: () => {
					frappe.hide_msgprint();
					onConfirm();
				},
			};
		}
		frappe.msgprint(options);
	}

	function show_result(result) {
		if (!result) return;
		const indicator =
			result.status === "ERROR" ? "red" : result.status === "QUEUED" ? "blue" : "green";
		let summary = "";
		if (result.status === "ERROR") {
			summary = `<p class="text-danger">${frappe.utils.escape_html(result.message || __("Chuyển kíp không thành công."))}</p>`;
		} else if (result.status === "QUEUED") {
			summary = `<p>${frappe.utils.escape_html(result.message || __("Yêu cầu chuyển kíp đã được đưa vào hàng đợi."))}</p>`;
		} else {
			summary = `<p>${__("Đã chuyển kíp thành công cho {0} nhân sự.", [result.employees || 0])}</p>
			<p>${__("Ca tự động đã hủy")}: ${result.cancelled_auto_assignments || 0} &nbsp; ${__("Ca tự động mới đã tạo")}: ${result.generation_counts?.CREATE || 0} &nbsp; ${__("Ngày nghỉ kíp")}: ${result.generation_counts?.OFF || 0}</p>`;
		}
		frappe.msgprint({
			title: __("Phân / chuyển kíp hàng loạt"),
			indicator,
			message: `${summary}<details><summary>${__("Chi tiết kỹ thuật")}</summary><pre style="max-height: 500px; overflow: auto">${frappe.utils.escape_html(JSON.stringify(result, null, 2))}</pre></details>`,
		});
	}
})();
