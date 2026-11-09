// Shared effective-dated Shift Group transfer dialog for Employee Form and List.

const VNTShiftGroupTransferUI = (() => {
	const PREVIEW_METHOD =
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.preview_shift_group_transfer";
	const EXECUTE_METHOD =
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.execute_shift_group_transfer";
	const BACKDATED_CONFIRMATION = "XÁC NHẬN HỒI TỐ";
	const BACKDATED_WARNING =
		"Chuyển kíp hồi tố sẽ tính lại dữ liệu chấm công đã có.";
	const queuedCompletionCallbacks = new Map();

	function isBackdated(effectiveDate, currentDate) {
		return Boolean(effectiveDate && currentDate && effectiveDate < currentDate);
	}

	function hasBackdatedRole(roles = []) {
		return roles.includes("HR Manager") || roles.includes("System Manager");
	}

	function buildPreviewCall({ values, employees, today, roles = [] }) {
		const backdated = isBackdated(values.effective_date, today);
		if (backdated && !hasBackdatedRole(roles)) {
			throw new Error(
				"Chỉ HR Manager hoặc System Manager được chuyển kíp hồi tố.",
			);
		}
		return {
			mode: backdated ? "BACKDATED" : "NORMAL",
			method: PREVIEW_METHOD,
			args: { ...values, employees: [...employees] },
			warning: backdated ? BACKDATED_WARNING : null,
		};
	}

	function canExecutePreview(preview) {
		if (!preview || (preview.counts?.BLOCKED || 0) > 0) return false;
		if (preview.mode !== "BACKDATED") return true;
		return Boolean(
			preview.batch_status === "READY" &&
				preview.can_execute === true &&
				preview.preview_token,
		);
	}

	function buildExecuteCall({ values, employees, preview, today, roles = [] }) {
		const backdated = isBackdated(values.effective_date, today);
		if (backdated && !hasBackdatedRole(roles)) {
			throw new Error(
				"Chỉ HR Manager hoặc System Manager được chuyển kíp hồi tố.",
			);
		}
		if (backdated && !canExecutePreview(preview)) {
			throw new Error("Preview hồi tố đang bị chặn hoặc đã hết hiệu lực.");
		}
		const args = { ...values, employees: [...employees] };
		if (backdated) {
			args.preview_token = preview.preview_token;
			// Clicking "Thực hiện hồi tố" on the preview, under its backdated
			// warning, is the confirmation; the server still requires the phrase.
			args.confirmation_text = BACKDATED_CONFIRMATION;
		}
		return {
			mode: backdated ? "BACKDATED" : "NORMAL",
			method: EXECUTE_METHOD,
			args,
		};
	}

	function openTransferDialog({
		frappe,
		employees,
		initialTargetShiftGroup = null,
		title = null,
		onCompleted = null,
	}) {
		const translate = translator();
		const dialog = new frappe.ui.Dialog({
			title:
				title ||
				translate("Phân / chuyển kíp ({0} nhân sự)", [employees.length]),
			fields: [
				{
					fieldname: "target_shift_group",
					fieldtype: "Link",
					options: "VNT Shift Group",
					label: translate("Kíp mới"),
					default: initialTargetShiftGroup,
					reqd: 1,
					get_query: () => ({ filters: { disabled: 0 } }),
					onchange: () => setGroupPeriodDefaults(frappe, dialog),
				},
				{
					fieldname: "effective_date",
					fieldtype: "Date",
					label: translate("Ngày hiệu lực"),
					default: frappe.datetime.get_today(),
					reqd: 1,
					onchange: () => {
						keepGenerateUntilInsideMembership(frappe, translate, dialog);
						updateBackdatedWarning(frappe, dialog);
					},
				},
				{ fieldname: "column_break_dates", fieldtype: "Column Break" },
				{
					fieldname: "membership_end_date",
					fieldtype: "Date",
					label: translate("Ngày kết thúc thuộc kíp"),
					reqd: 1,
					onchange: () =>
						keepGenerateUntilInsideMembership(frappe, translate, dialog),
				},
				{
					fieldname: "generate_until",
					fieldtype: "Date",
					label: translate("Tạo ca kế hoạch đến ngày"),
					reqd: 1,
					hidden: 1,
					onchange: () =>
						keepGenerateUntilInsideMembership(frappe, translate, dialog),
				},
				{
					fieldname: "note",
					fieldtype: "Small Text",
					label: translate("Lý do / Ghi chú"),
					reqd: 1,
				},
				{
					fieldname: "backdated_warning",
					fieldtype: "HTML",
					options: `<div class="alert alert-danger mb-0"><strong>${translate(
						BACKDATED_WARNING,
					)}</strong><br>${translate(
						"Chỉ HR Manager/System Manager được thực hiện; hãy xem kỹ blocker, punch được giữ và action plan.",
					)}</div>`,
				},
			],
			primary_action_label: translate("Xem trước"),
			primary_action(values) {
				if (!validateTransferPeriod(frappe, translate, values)) return;
				let call;
				try {
					call = buildPreviewCall({
						values,
						employees,
						today: frappe.datetime.get_today(),
						roles: currentRoles(frappe),
					});
				} catch (error) {
					frappe.msgprint(translate(error.message));
					return;
				}
				frappe.call({
					method: call.method,
					args: call.args,
					freeze: true,
					freeze_message:
						call.mode === "BACKDATED"
							? translate("Đang kiểm tra dữ liệu hồi tố và blocker...")
							: translate("Đang kiểm tra kíp và ca kế hoạch..."),
					callback: (response) => {
						const preview = response.message;
						const onConfirm = canExecutePreview(preview)
							? () => {
								dialog.hide();
								executeTransfer({
									frappe,
									translate,
									values,
									employees,
									preview,
									onCompleted,
								});
							}
							: null;
						showPreview(frappe, translate, preview, onConfirm);
					},
				});
			},
		});
		dialog.show();
		if (initialTargetShiftGroup) {
			setGroupPeriodDefaults(frappe, dialog);
		}
		updateBackdatedWarning(frappe, dialog);
		return dialog;
	}

	function executeTransfer({
		frappe,
		translate,
		values,
		employees,
		preview,
		onCompleted = null,
	}) {
		let call;
		try {
			call = buildExecuteCall({
				values,
				employees,
				preview,
				today: frappe.datetime.get_today(),
				roles: currentRoles(frappe),
			});
		} catch (error) {
			frappe.msgprint(translate(error.message));
			return;
		}
		frappe.call({
			method: call.method,
			args: call.args,
			freeze: true,
			freeze_message:
				call.mode === "BACKDATED"
					? translate("Đang tính lại ca, chấm công và phiếu giải trình...")
					: translate("Đang thực hiện phân / chuyển kíp..."),
			callback: (response) =>
				handleExecutionResult(
					frappe,
					translate,
					response.message,
					onCompleted,
					{
						effectiveDate: values.effective_date,
						today: frappe.datetime.get_today(),
					},
				),
		});
	}

	function handleExecutionResult(
		frappe,
		translate,
		result,
		onCompleted = null,
		context = {},
	) {
		showResult(frappe, translate, result, context);
		if (!result) return;
		if (result.status === "QUEUED") {
			if (onCompleted) {
				queuedCompletionCallbacks.set(result.job_id || "__unkeyed__", onCompleted);
			}
			return;
		}
		if (
			onCompleted &&
			(result.status === "COMPLETED" || result.status === "ALREADY_APPLIED")
		) {
			onCompleted(result);
		}
	}

	function handleRealtimeResult(frappe, translate, result) {
		showResult(frappe, translate, result, {});
		if (!result) return;
		const successful =
			result.status === "COMPLETED" || result.status === "ALREADY_APPLIED";
		if (result.job_id && queuedCompletionCallbacks.has(result.job_id)) {
			const callback = queuedCompletionCallbacks.get(result.job_id);
			queuedCompletionCallbacks.delete(result.job_id);
			if (successful) callback(result);
			return;
		}
		for (const [jobId, callback] of queuedCompletionCallbacks.entries()) {
			queuedCompletionCallbacks.delete(jobId);
			if (successful) callback(result);
		}
	}

	const BLOCKER_REASONS = {
		BATCH_LIMIT_EXCEEDED: "Vượt quá số nhân sự tối đa cho một lần chuyển kíp hồi tố.",
		NOT_BACKDATED: "Ngày hiệu lực phải trước ngày hôm nay.",
		MEMBERSHIP_END_BEFORE_TODAY: "Ngày kết thúc thuộc kíp không được trước ngày hôm nay.",
		INVALID_DATE_RANGE: "Ngày hiệu lực không được sau ngày kết thúc thuộc kíp.",
		INVALID_GENERATE_UNTIL: "Ngày tạo ca phải nằm trong khoảng thuộc kíp.",
		DATE_RANGE_EXCEEDED: "Khoảng chuyển kíp hồi tố vượt quá số ngày cho phép.",
		EMPLOYEE_NOT_ACTIVE: "Nhân sự không còn ở trạng thái Active.",
		TARGET_GROUP_MISSING: "Kíp mới không tồn tại.",
		TARGET_GROUP_DISABLED: "Kíp mới đang bị vô hiệu hóa.",
		COMPANY_MISMATCH: "Công ty của nhân sự khác công ty của kíp mới.",
		TARGET_GROUP_OUTSIDE_PERIOD: "Khoảng chuyển nằm ngoài thời gian hiệu lực của kíp mới.",
		OVERLAPPING_MEMBERSHIPS: "Có nhiều membership kíp cùng hiệu lực tại ngày hiệu lực.",
		FUTURE_MEMBERSHIP_OVERLAP: "Có membership kíp khác trùng khoảng chuyển.",
		TARGET_SCHEDULE_MISSING: "Kíp mới thiếu lịch cho một số ngày trong tuần.",
		TARGET_SHIFT_TYPE_MISSING: "Lịch của kíp mới có ngày không có ca hợp lệ.",
		OVERLAPPING_SHIFT_ASSIGNMENTS: "Có nhiều ca kế hoạch trùng cùng một ngày.",
		MANUAL_SHIFT_ASSIGNMENT: "Có ca kế hoạch tạo tay hoặc dữ liệu cũ, không thể ghi lại tự động.",
		CURRENT_WORK_DATE_DATA:
			"Đã có bản ghi chấm công (Attendance) của ngày hôm nay; không thể tính lại ngày hôm nay.",
		MULTIPLE_ACTIVE_ATTENDANCE: "Có nhiều bản ghi chấm công trong cùng một ngày.",
		PROTECTED_ATTENDANCE_SOURCE: "Có ngày nghỉ phép hoặc đơn chấm công, không thể tính lại.",
		AMBIGUOUS_LEGACY_ATTENDANCE:
			"Có chấm công cũ không rõ nguồn (thiếu checkin hoặc ca kế hoạch tự động).",
		CONFIRMED_ATTENDANCE_EXPLANATION:
			"Có phiếu giải trình đã được HR xác nhận trong khoảng hồi tố.",
		SUBMITTED_SALARY_SLIP: "Đã có phiếu lương được duyệt trong khoảng hồi tố.",
	};

	function blockerReason(blocker, translate) {
		if (typeof blocker === "string") return blocker;
		const reason = BLOCKER_REASONS[blocker?.code];
		return reason ? translate(reason) : blocker?.message || blocker?.code || "";
	}

	function renderStatus(row, translate, escape) {
		if (row.status !== "BLOCKED") {
			return `<span class="text-success">${translate("Sẵn sàng")}</span>`;
		}
		const reasons = (row.blockers || [])
			.map((blocker) => blockerReason(blocker, translate))
			.filter(Boolean)
			.map((reason) => `<div class="small">${escape(reason)}</div>`);
		return `<span class="text-danger"><strong>${translate("Bị chặn")}</strong>${reasons.join(
			"",
		)}</span>`;
	}

	function buildPreviewMessage(preview, translate, escape) {
		const rows = (preview.rows || []).slice(0, 100).map((row) => {
			const targetShiftGroup =
				row.target_shift_group || row.membership_action?.target_shift_group || "-";
			return `<tr>
				<td>${escape(row.employee)}</td>
				<td>${escape(row.employee_name || "")}</td>
				<td>${escape(row.authoritative_shift_group || row.current_shift_group || "-")}</td>
				<td>${escape(row.display_shift_group || "-")}</td>
				<td>${escape(targetShiftGroup)}</td>
				<td>${renderStatus(row, translate, escape)}</td>
			</tr>`;
		});
		return `
			${
				preview.mode === "BACKDATED"
					? `<div class="alert alert-danger"><strong>${translate(
						BACKDATED_WARNING,
					)}</strong></div><p>${translate("Hoàn tất tính đến")}: ${escape(
						preview.completed_through || "",
					)}</p>`
					: ""
			}
			<p>${translate("Sẵn sàng")}: ${preview.counts?.READY || 0} &nbsp; ${translate(
				"Bị chặn",
			)}: ${preview.counts?.BLOCKED || 0}</p>
			<div class="table-responsive"><table class="table table-bordered table-sm">
				<thead><tr><th>${translate("Mã nhân viên")}</th><th>${translate(
					"Tên nhân viên",
				)}</th><th>${translate("Kíp theo membership")}</th><th>${translate(
					"Kíp đang hiển thị",
				)}</th><th>${translate("Kíp mới")}</th><th>${translate(
					"Trạng thái",
				)}</th></tr></thead>
				<tbody>${rows.join("")}</tbody>
			</table></div>`;
	}

	function showPreview(frappe, translate, preview, onConfirm) {
		const options = {
			title:
				preview.mode === "BACKDATED"
					? translate("Xem trước chuyển kíp hồi tố")
					: translate("Xem trước phân / chuyển kíp"),
			wide: true,
			message: buildPreviewMessage(preview, translate, (value) =>
				escapeHtml(frappe, value),
			),
		};
		if (onConfirm) {
			options.primary_action = {
				label:
					preview.mode === "BACKDATED"
						? translate("Thực hiện hồi tố")
						: translate("Xác nhận chuyển kíp"),
				action: () => {
					frappe.hide_msgprint();
					onConfirm();
				},
			};
		}
		frappe.msgprint(options);
	}

	function showResult(frappe, translate, result, context = {}) {
		if (!result) return;
		const escape = (value) => escapeHtml(frappe, value);
		const indicator =
			result.status === "ERROR"
				? "red"
				: result.status === "QUEUED"
					? "blue"
					: "green";
		let summary;
		if (result.status === "ERROR") {
			summary = `<p class="text-danger">${escape(
				result.message || translate("Chuyển kíp không thành công."),
			)}</p>`;
		} else if (result.status === "QUEUED") {
			summary = `<p>${escape(
				result.message || translate("Yêu cầu chuyển kíp đã được đưa vào hàng đợi."),
			)}</p>`;
		} else if (result.status === "ALREADY_APPLIED") {
			summary = `<p>${translate(
				"Yêu cầu đã được áp dụng trước đó; không ghi thêm dữ liệu.",
			)}</p>`;
		} else if (
			context.effectiveDate &&
			context.today &&
			context.effectiveDate > context.today
		) {
			summary = `<p>${translate(
				"Đã lên lịch chuyển kíp cho {0} nhân sự; Kíp hiện tại sẽ đổi vào ngày hiệu lực.",
				[result.employees || 0],
			)}</p>`;
		} else {
			summary = `<p>${translate("Đã chuyển kíp thành công cho {0} nhân sự.", [
				result.employees || 0,
			])}</p>`;
		}
		frappe.msgprint({
			title: translate("Phân / chuyển kíp"),
			indicator,
			message: `${summary}<details><summary>${translate(
				"Chi tiết kỹ thuật",
			)}</summary><pre style="max-height: 500px; overflow: auto">${escape(
				JSON.stringify(result, null, 2),
			)}</pre></details>`,
		});
	}

	function validateTransferPeriod(frappe, translate, values) {
		if (values.effective_date > values.membership_end_date) {
			frappe.msgprint(translate("Ngày hiệu lực không được sau ngày kết thúc thuộc kíp."));
			return false;
		}
		if (
			values.generate_until < values.effective_date ||
			values.generate_until > values.membership_end_date
		) {
			frappe.msgprint(translate("Ngày tạo ca phải nằm trong khoảng thuộc kíp."));
			return false;
		}
		return true;
	}

	function updateBackdatedWarning(frappe, dialog) {
		const field = dialog.get_field("backdated_warning");
		if (!field?.$wrapper) return;
		field.$wrapper.toggle(
			isBackdated(dialog.get_value("effective_date"), frappe.datetime.get_today()),
		);
	}

	function setGroupPeriodDefaults(frappe, dialog) {
		const shiftGroup = dialog.get_value("target_shift_group");
		if (!shiftGroup || !frappe.db) return;
		frappe.db
			.get_value("VNT Shift Group", shiftGroup, ["effective_from", "effective_to"])
			.then((response) => {
				const period = response.message || {};
				if (
					period.effective_from &&
					dialog.get_value("effective_date") < period.effective_from
				) {
					dialog.set_value("effective_date", period.effective_from);
				}
				if (period.effective_to) {
					dialog.set_value("membership_end_date", period.effective_to);
					dialog.set_value("generate_until", period.effective_to);
				}
			});
	}

	function keepGenerateUntilInsideMembership(frappe, translate, dialog) {
		const effectiveDate = dialog.get_value("effective_date");
		const membershipEndDate = dialog.get_value("membership_end_date");
		const generateUntil = dialog.get_value("generate_until");
		if (!generateUntil) return;
		let adjusted = generateUntil;
		if (effectiveDate && adjusted < effectiveDate) adjusted = effectiveDate;
		if (membershipEndDate && adjusted > membershipEndDate) adjusted = membershipEndDate;
		if (adjusted !== generateUntil) {
			dialog.set_value("generate_until", adjusted);
			frappe.show_alert?.({
				message: translate(
					"Ngày tạo ca đã được điều chỉnh để nằm trong khoảng thuộc kíp.",
				),
				indicator: "orange",
			});
		}
	}

	function currentRoles(frappe) {
		return ["HR User", "HR Manager", "System Manager"].filter((role) =>
			frappe.user.has_role(role),
		);
	}

	function translator() {
		return typeof __ === "function" ? __ : (value) => value;
	}

	function escapeHtml(frappe, value) {
		return frappe.utils?.escape_html
			? frappe.utils.escape_html(String(value ?? ""))
			: String(value ?? "");
	}

	return {
		BACKDATED_CONFIRMATION,
		buildExecuteCall,
		buildPreviewMessage,
		buildPreviewCall,
		canExecutePreview,
		handleExecutionResult,
		handleRealtimeResult,
		isBackdated,
		openTransferDialog,
	};
})();

if (typeof module !== "undefined" && module.exports) {
	module.exports = VNTShiftGroupTransferUI;
}

if (typeof globalThis !== "undefined") {
	globalThis.VNTShiftGroupTransferUI = VNTShiftGroupTransferUI;
}
