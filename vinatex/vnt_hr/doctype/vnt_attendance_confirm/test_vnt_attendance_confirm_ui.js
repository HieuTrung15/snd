const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const doctypeDir = __dirname;

function translate(message, values) {
	if (!values) return message;
	return values.reduce(
		(text, value, index) => text.replace(`{${index}}`, String(value)),
		message
	);
}

function loadScript(filename, context) {
	const source = fs.readFileSync(path.join(doctypeDir, filename), "utf8");
	vm.runInNewContext(source, context, { filename });
}

test("list update result displays the number of deleted confirmations", () => {
	let updateButton;
	let message;
	const frappe = {
		listview_settings: {},
		datetime: {
			obj_to_str(value) {
				return value.toISOString().slice(0, 10);
			},
		},
		call(options) {
			options.callback({
				message: {
					"Số ngày bất thường": 3,
					"Ngày làm việc về sớm": 1,
					"Số phiếu tạo mới": 0,
					"Số phiếu cập nhật": 1,
					"Số phiếu đã xóa": 2,
				},
			});
		},
		msgprint(options) {
			message = options.message;
		},
	};
	const listview = {
		get_filters_for_args() {
			return [];
		},
		page: {
			add_inner_button(label, callback) {
				if (label === "Cập nhật bất thường tháng này") updateButton = callback;
			},
			fields_dict: {},
		},
		refresh() {},
	};

	loadScript("vnt_attendance_confirm_list.js", {
		Date,
		frappe,
		__: translate,
	});
	frappe.listview_settings["VNT Attendance Confirm"].onload(listview);
	updateButton();

	assert.match(message, /Số phiếu đã xóa: 2/);
});

test("form refresh routes to the list when the open confirmation is deleted", () => {
	const handlers = {};
	const buttons = {};
	const routes = [];
	let reloadCount = 0;
	const frappe = {
		ui: {
			form: {
				on(doctype, events) {
					handlers[doctype] = events;
				},
			},
		},
		model: { set_value() {} },
		call(options) {
			options.callback({ message: { "Số phiếu đã xóa": 1 } });
		},
		show_alert() {},
		set_route(...route) {
			routes.push(route);
		},
		prompt() {},
	};
	const frm = {
		doc: {
			name: "GTCC-NMSVNĐ00175-2026-11",
			status: "Chờ giải trình",
			items: [],
			bulk_explanation: "",
		},
		doctype: "VNT Attendance Confirm",
		fields_dict: {},
		set_df_property() {},
		is_new() {
			return false;
		},
		add_custom_button(label, callback) {
			buttons[label] = callback;
		},
		reload_doc() {
			reloadCount += 1;
		},
	};

	loadScript("vnt_attendance_confirm.js", {
		frappe,
		__: translate,
		refresh_field() {},
	});
	handlers["VNT Attendance Confirm"].refresh(frm);
	buttons["Cập nhật dữ liệu bất thường"]();

	assert.deepEqual(routes, [["List", "VNT Attendance Confirm"]]);
	assert.equal(reloadCount, 0);
});
