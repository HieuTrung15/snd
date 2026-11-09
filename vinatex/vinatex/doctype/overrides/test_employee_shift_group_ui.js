const test = require("node:test");
const assert = require("node:assert/strict");

global.frappe = {
	ui: { form: { on() {} } },
	session: { user: "Administrator" },
};
global.__ = (value) => value;

const {
	captureShiftGroupBaseline,
	handleShiftGroupChange,
	hasNonShiftGroupChanges,
	rememberShiftGroupBaseline,
} = require("./employee.js");

function makeFrappe(roles = ["HR Manager"]) {
	const messages = [];
	return {
		user: { has_role: (role) => roles.includes(role) },
		msgprint(message) {
			messages.push(message);
		},
		messages,
	};
}

function makeForm({ shiftGroup = "4", isNew = false } = {}) {
	let reloads = 0;
	let saves = 0;
	const frm = {
		doc: {
			doctype: "Employee",
			name: isNew ? "new-employee-1" : "EMP-001",
			custom_shift_group: shiftGroup,
			department: "Spinning",
			education: [{ name: "ROW-1", school_univ: "School" }],
			__unsaved: isNew ? 1 : 0,
		},
		is_new: () => isNew,
		async set_value(fieldname, value) {
			this.doc[fieldname] = value;
			this.doc.__unsaved = 1;
		},
		async reload_doc() {
			reloads += 1;
		},
		async save() {
			saves += 1;
		},
	};
	frm.__vnt_shift_group_baseline = captureShiftGroupBaseline(frm);
	return {
		frm,
		get reloads() {
			return reloads;
		},
		get saves() {
			return saves;
		},
	};
}

test("saved Employee reverts the field and opens the shared effective-date dialog", async () => {
	const state = makeForm();
	const frappe = makeFrappe();
	let openedWith;
	const transferUI = {
		openTransferDialog(options) {
			openedWith = options;
		},
	};
	state.frm.doc.custom_shift_group = "3";

	await handleShiftGroupChange(state.frm, frappe, transferUI);

	assert.equal(state.frm.doc.custom_shift_group, "4");
	assert.deepEqual(openedWith.employees, ["EMP-001"]);
	assert.equal(openedWith.initialTargetShiftGroup, "3");
	assert.equal(typeof openedWith.onCompleted, "function");
	assert.equal(state.saves, 0);
});

test("cancelled or blocked preview leaves the saved source group untouched", async () => {
	const state = makeForm();
	let openedWith;
	state.frm.doc.custom_shift_group = "3";

	await handleShiftGroupChange(state.frm, makeFrappe(), {
		openTransferDialog(options) {
			openedWith = options;
		},
	});

	assert.ok(openedWith);
	assert.equal(state.frm.doc.custom_shift_group, "4");
	assert.equal(state.frm.doc.__unsaved, 0);
	assert.equal(state.saves, 0);
});

test("successful execution reloads the Employee document", async () => {
	const state = makeForm();
	let openedWith;
	state.frm.doc.custom_shift_group = "3";
	await handleShiftGroupChange(state.frm, makeFrappe(), {
		openTransferDialog(options) {
			openedWith = options;
		},
	});

	await openedWith.onCompleted({ status: "COMPLETED" });

	assert.equal(state.reloads, 1);
});

test("unrelated dirty data is detected including child rows", () => {
	const state = makeForm();
	assert.equal(hasNonShiftGroupChanges(state.frm.__vnt_shift_group_baseline, state.frm.doc), false);
	state.frm.doc.education[0].school_univ = "Changed school";
	assert.equal(hasNonShiftGroupChanges(state.frm.__vnt_shift_group_baseline, state.frm.doc), true);
});

test("unrelated dirty field is preserved while transfer dialog is refused", async () => {
	const state = makeForm();
	const frappe = makeFrappe();
	let opens = 0;
	state.frm.doc.department = "Packing";
	state.frm.doc.custom_shift_group = "3";

	await handleShiftGroupChange(state.frm, frappe, {
		openTransferDialog() {
			opens += 1;
		},
	});

	assert.equal(state.frm.doc.custom_shift_group, "4");
	assert.equal(state.frm.doc.department, "Packing");
	assert.equal(opens, 0);
	assert.match(frappe.messages.join(" "), /lưu.*thay đổi/i);
});

test("clear target, missing role and duplicate onchange do not create invalid requests", async () => {
	const clearState = makeForm();
	let opens = 0;
	clearState.frm.doc.custom_shift_group = null;
	await handleShiftGroupChange(clearState.frm, makeFrappe(), {
		openTransferDialog() {
			opens += 1;
		},
	});
	assert.equal(clearState.frm.doc.custom_shift_group, "4");
	assert.equal(opens, 0);

	const noRoleState = makeForm();
	noRoleState.frm.doc.custom_shift_group = "3";
	await handleShiftGroupChange(noRoleState.frm, makeFrappe([]), {
		openTransferDialog() {
			opens += 1;
		},
	});
	assert.equal(noRoleState.frm.doc.custom_shift_group, "4");
	assert.equal(opens, 0);

	const duplicateState = makeForm();
	duplicateState.frm.doc.custom_shift_group = "3";
	duplicateState.frm.set_value = async function (fieldname, value) {
		await new Promise((resolve) => setImmediate(resolve));
		this.doc[fieldname] = value;
	};
	const transferUI = {
		openTransferDialog() {
			opens += 1;
		},
	};
	await Promise.all([
		handleShiftGroupChange(duplicateState.frm, makeFrappe(), transferUI),
		handleShiftGroupChange(duplicateState.frm, makeFrappe(), transferUI),
	]);
	assert.equal(opens, 1);
});

test("new Employee must be saved before selecting a shift group", async () => {
	const state = makeForm({ shiftGroup: null, isNew: true });
	const frappe = makeFrappe();
	let opens = 0;
	state.frm.doc.custom_shift_group = "3";

	await handleShiftGroupChange(state.frm, frappe, {
		openTransferDialog() {
			opens += 1;
		},
	});

	assert.equal(state.frm.doc.custom_shift_group, null);
	assert.equal(opens, 0);
	assert.match(frappe.messages.join(" "), /lưu hồ sơ/i);
});

test("reused Employee Form keeps a separate saved baseline for every document", async () => {
	let opens = 0;
	const frappe = makeFrappe();
	const employeeA = {
		doctype: "Employee",
		name: "EMP-A",
		custom_shift_group: "4",
		department: "Spinning",
		__unsaved: 0,
	};
	const employeeB = {
		doctype: "Employee",
		name: "EMP-B",
		custom_shift_group: "2",
		department: "Packing",
		__unsaved: 0,
	};
	const frm = {
		doc: employeeA,
		is_new() {
			return this.doc.name.startsWith("new-");
		},
		async set_value(fieldname, value) {
			this.doc[fieldname] = value;
			this.doc.__unsaved = 1;
		},
		refresh_header() {},
		async reload_doc() {},
	};
	const transferUI = {
		openTransferDialog() {
			opens += 1;
		},
	};

	rememberShiftGroupBaseline(frm);
	employeeA.department = "Changed but unsaved";
	employeeA.__unsaved = 1;
	frm.doc = employeeB;
	rememberShiftGroupBaseline(frm);
	frm.doc = employeeA;
	rememberShiftGroupBaseline(frm);
	employeeA.custom_shift_group = "3";
	await handleShiftGroupChange(frm, frappe, transferUI);

	assert.equal(employeeA.custom_shift_group, "4");
	assert.equal(employeeA.department, "Changed but unsaved");
	assert.equal(opens, 0);
	assert.match(frappe.messages.join(" "), /lưu.*thay đổi/i);

	frm.doc = {
		doctype: "Employee",
		name: "new-employee-2",
		custom_shift_group: null,
		department: null,
		__unsaved: 1,
	};
	rememberShiftGroupBaseline(frm);
	frm.doc.custom_shift_group = "3";
	await handleShiftGroupChange(frm, frappe, transferUI);

	assert.equal(frm.doc.custom_shift_group, null);
	assert.equal(opens, 0);
	assert.match(frappe.messages.join(" "), /lưu hồ sơ/i);
});
