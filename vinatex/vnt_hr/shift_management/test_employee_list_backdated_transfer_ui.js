const test = require("node:test");
const assert = require("node:assert/strict");

const { setupDesk } = require("./employee_list.js");

test("Employee List delegates selected employees to the shared transfer dialog", () => {
	let action;
	let openedWith;
	const realtimeHandlers = {};
	const transferUI = {
		openTransferDialog(options) {
			openedWith = options;
		},
		handleRealtimeResult() {},
	};
	const frappe = {
		listview_settings: {},
		user: { has_role: () => true },
		realtime: {
			on(event, handler) {
				realtimeHandlers[event] = handler;
			},
		},
		msgprint() {},
	};
	const listview = {
		page: {
			add_actions_menu_item(_label, handler) {
				action = handler;
			},
		},
		get_checked_items: () => [{ name: "EMP-001" }, { name: "EMP-002" }],
		refresh() {},
	};

	setupDesk(frappe, transferUI);
	frappe.listview_settings.Employee.onload(listview);
	action();

	assert.deepEqual(openedWith.employees, ["EMP-001", "EMP-002"]);
	assert.equal(openedWith.frappe, frappe);
	assert.equal(typeof openedWith.onCompleted, "function");
	assert.equal(
		typeof realtimeHandlers.vnt_bulk_shift_group_transfer_completed,
		"function",
	);
});
