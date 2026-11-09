const test = require("node:test");
const assert = require("node:assert/strict");

const UI = require("../../public/js/shift_group_transfer_dialog.js");

const TODAY = "2026-11-05";
const baseValues = {
	target_shift_group: "3",
	effective_date: "2026-11-01",
	membership_end_date: "2026-12-31",
	generate_until: "2026-12-31",
	note: "Approved transfer",
};

test("all effective dates use the unified preview facade", () => {
	for (const [effectiveDate, expectedMode, roles] of [
		["2026-11-01", "BACKDATED", ["HR Manager"]],
		["2026-11-05", "NORMAL", ["HR User"]],
		["2026-11-06", "NORMAL", ["HR User"]],
	]) {
		const call = UI.buildPreviewCall({
			values: { ...baseValues, effective_date: effectiveDate },
			employees: ["EMP-001"],
			today: TODAY,
			roles,
		});
		assert.equal(call.mode, expectedMode);
		assert.equal(
			call.method,
			"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.preview_shift_group_transfer",
		);
	}
});

test("backdated preview and execute retain manager and token safeguards", () => {
	assert.throws(
		() =>
			UI.buildPreviewCall({
				values: baseValues,
				employees: ["EMP-001"],
				today: TODAY,
				roles: ["HR User"],
			}),
		/HR Manager.*System Manager/,
	);

	const preview = {
		mode: "BACKDATED",
		batch_status: "READY",
		can_execute: true,
		preview_token: "token-1",
		counts: { READY: 1 },
	};
	assert.throws(
		() =>
			UI.buildExecuteCall({
				values: baseValues,
				employees: ["EMP-001"],
				preview: { ...preview, preview_token: null },
				today: TODAY,
				roles: ["HR Manager"],
			}),
		/hết hiệu lực/,
	);

	const call = UI.buildExecuteCall({
		values: baseValues,
		employees: ["EMP-001"],
		preview,
		today: TODAY,
		roles: ["HR Manager"],
	});
	assert.equal(
		call.method,
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.execute_shift_group_transfer",
	);
	assert.equal(call.args.preview_token, "token-1");
	assert.equal(call.args.confirmation_text, UI.BACKDATED_CONFIRMATION);
});

test("blocked preview never becomes executable", () => {
	assert.equal(
		UI.canExecutePreview({
			mode: "BACKDATED",
			batch_status: "BLOCKED",
			can_execute: false,
			preview_token: "token-1",
			counts: { BLOCKED: 1 },
		}),
		false,
	);
	assert.equal(
		UI.canExecutePreview({ mode: "NORMAL", counts: { BLOCKED: 1 } }),
		false,
	);
});

test("dialog pre-fills the target selected on Employee form", () => {
	class FakeDialog {
		constructor(config) {
			this.config = config;
			this.values = Object.fromEntries(
				config.fields
					.filter((field) => field.fieldname)
					.map((field) => [field.fieldname, field.default ?? null]),
			);
		}
		show() {
			this.shown = true;
		}
		get_value(fieldname) {
			return this.values[fieldname];
		}
		set_value(fieldname, value) {
			this.values[fieldname] = value;
			return Promise.resolve();
		}
		get_field() {
			return { $wrapper: { toggle() {} } };
		}
	}
	const frappe = {
		ui: { Dialog: FakeDialog },
		datetime: { get_today: () => TODAY },
		user: { has_role: () => true },
	};

	const dialog = UI.openTransferDialog({
		frappe,
		employees: ["EMP-001"],
		initialTargetShiftGroup: "3",
	});

	assert.equal(dialog.get_value("target_shift_group"), "3");
	assert.equal(dialog.get_value("effective_date"), TODAY);
	assert.equal(dialog.shown, true);
});

test("pre-filled target immediately loads its valid membership period", async () => {
	class FakeDialog {
		constructor(config) {
			this.values = Object.fromEntries(
				config.fields
					.filter((field) => field.fieldname)
					.map((field) => [field.fieldname, field.default ?? null]),
			);
		}
		show() {}
		get_value(fieldname) {
			return this.values[fieldname];
		}
		set_value(fieldname, value) {
			this.values[fieldname] = value;
			return Promise.resolve();
		}
		get_field() {
			return { $wrapper: { toggle() {} } };
		}
	}
	const frappe = {
		ui: { Dialog: FakeDialog },
		datetime: { get_today: () => TODAY },
		user: { has_role: () => true },
		db: {
			get_value: async () => ({
				message: { effective_from: "2026-01-01", effective_to: "2026-12-31" },
			}),
		},
	};

	const dialog = UI.openTransferDialog({
		frappe,
		employees: ["EMP-001"],
		initialTargetShiftGroup: "3",
	});
	await new Promise((resolve) => setImmediate(resolve));

	assert.equal(dialog.get_value("membership_end_date"), "2026-12-31");
	assert.equal(dialog.get_value("generate_until"), "2026-12-31");
});

test("completion callback runs only after completed result or queued realtime result", () => {
	let completed = 0;
	const messages = [];
	const frappe = {
		msgprint: (options) => messages.push(options.message),
		utils: { escape_html: (value) => String(value) },
	};
	const translate = (value) => value;

	UI.handleExecutionResult(
		frappe,
		translate,
		{ status: "ERROR", message: "failed" },
		() => completed++,
		{ effectiveDate: "2026-11-01", today: TODAY },
	);
	assert.equal(completed, 0);

	UI.handleExecutionResult(
		frappe,
		translate,
		{ status: "QUEUED", job_id: "job-1", message: "queued" },
		() => completed++,
		{ effectiveDate: "2026-11-06", today: TODAY },
	);
	assert.equal(completed, 0);

	UI.handleRealtimeResult(frappe, translate, {
		status: "COMPLETED",
		job_id: "job-1",
		employees: 1,
	});
	assert.equal(completed, 1);

	UI.handleExecutionResult(
		frappe,
		translate,
		{ status: "ALREADY_APPLIED", employees: 1 },
		() => completed++,
		{ effectiveDate: "2026-11-01", today: TODAY },
	);
	assert.equal(completed, 2);
	assert.ok(messages.length >= 4);
});

test("future transfer result explicitly says it is scheduled", () => {
	const messages = [];
	const frappe = {
		msgprint: (options) => messages.push(options.message),
		utils: { escape_html: (value) => String(value) },
	};

	UI.handleExecutionResult(
		frappe,
		(value) => value,
		{ status: "COMPLETED", employees: 1 },
		() => {},
		{ effectiveDate: "2026-11-06", today: TODAY },
	);

	assert.match(messages.at(-1), /lên lịch/i);
});

test("preview table has no Details column and shows a short block reason", () => {
	const html = UI.buildPreviewMessage(
		{
			mode: "BACKDATED",
			completed_through: "2026-11-08",
			counts: { BLOCKED: 1 },
			rows: [
				{
					employee: "NMSVNĐ00105",
					employee_name: "Trần Thị Đỉnh",
					authoritative_shift_group: "1",
					display_shift_group: "1",
					status: "BLOCKED",
					membership_action: { action: "CLOSE_SOURCE_CREATE_TARGET", target_shift_group: "HC" },
					blockers: [
						{
							code: "CURRENT_WORK_DATE_DATA",
							message: "Attendance for today's work date cannot be rebuilt.",
							references: ["HR-ATT-2026-06600"],
						},
					],
					attendance_actions: [
						{ work_date: "2026-11-01", action: "CANCEL_REBUILD", attendance: "HR-ATT-2026-05418" },
					],
					assignment_actions: [],
				},
			],
		},
		(value) => value,
		(value) => String(value),
	);

	assert.doesNotMatch(html, /Chi tiết/);
	assert.doesNotMatch(html, /CANCEL_REBUILD|CLOSE_SOURCE_CREATE_TARGET/);
	assert.equal((html.match(/<th>/g) || []).length, 6);
	assert.match(html, />HC</);
	assert.match(html, /Bị chặn/);
	assert.match(html, /bản ghi chấm công \(Attendance\) của ngày hôm nay/);
});

test("normal-mode string blockers are shown as the reason", () => {
	const html = UI.buildPreviewMessage(
		{
			mode: "NORMAL",
			counts: { BLOCKED: 1 },
			rows: [
				{ employee: "E1", status: "BLOCKED", blockers: ["Lý do chặn A"] },
				{ employee: "E2", status: "READY", blockers: [] },
			],
		},
		(value) => value,
		(value) => String(value),
	);

	assert.match(html, /Lý do chặn A/);
	assert.match(html, /Sẵn sàng/);
});

test("backdated preview executes directly without a typed confirmation popup", () => {
	const dialogs = [];
	class FakeDialog {
		constructor(config) {
			this.config = config;
			this.values = Object.fromEntries(
				config.fields
					.filter((field) => field.fieldname)
					.map((field) => [field.fieldname, field.default ?? null]),
			);
			dialogs.push(this);
		}
		show() {}
		hide() {
			this.hidden = true;
		}
		get_value(fieldname) {
			return this.values[fieldname];
		}
		set_value(fieldname, value) {
			this.values[fieldname] = value;
			return Promise.resolve();
		}
		get_field() {
			return { $wrapper: { toggle() {} } };
		}
	}
	const calls = [];
	const messages = [];
	const frappe = {
		ui: { Dialog: FakeDialog },
		datetime: { get_today: () => TODAY },
		user: { has_role: () => true },
		utils: { escape_html: (value) => String(value) },
		call: (options) => {
			calls.push(options);
			if (calls.length === 1) {
				options.callback({
					message: {
						mode: "BACKDATED",
						batch_status: "READY",
						can_execute: true,
						preview_token: "token-1",
						completed_through: "2026-11-04",
						counts: { READY: 1 },
						rows: [],
					},
				});
			}
		},
		msgprint: (options) => messages.push(options),
		hide_msgprint: () => {},
	};

	const dialog = UI.openTransferDialog({ frappe, employees: ["EMP-001"] });
	dialog.config.primary_action(baseValues);

	const preview = messages.at(-1);
	assert.equal(preview.primary_action.label, "Thực hiện hồi tố");
	preview.primary_action.action();

	assert.equal(dialogs.length, 1);
	assert.equal(dialog.hidden, true);
	assert.equal(calls.length, 2);
	assert.equal(
		calls[1].method,
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.execute_shift_group_transfer",
	);
	assert.equal(calls[1].args.preview_token, "token-1");
	assert.equal(calls[1].args.confirmation_text, UI.BACKDATED_CONFIRMATION);
});
