// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

const LEVEL_SALARY_FIELDS = Array.from({ length: 12 }, (_, index) => ({
	coefficient: `${index + 1}`,
	salary: `ml_b${index + 1}`,
}));

const hasValue = (value) => value !== undefined && value !== null && value !== "";

const updateItemLevelSalaries = (frm, item) => {
	if (!item) {
		return;
	}

	const baseSalary = frappe.utils.flt(frm.doc.corporate_minimum_wage);
	if (!baseSalary) {
		return;
	}

	LEVEL_SALARY_FIELDS.forEach(({ coefficient, salary }) => {
		if (!hasValue(item[coefficient])) {
			return;
		}

		const coefficientValue = frappe.utils.flt(item[coefficient]);
		if (!coefficientValue) {
			return;
		}

		frappe.model.set_value(item.doctype, item.name, salary, baseSalary * coefficientValue);
	});
};

const updateSalaryFieldsForEvent = (frm, cdt, cdn) => {
	const item = locals?.[cdt]?.[cdn];
	updateItemLevelSalaries(frm, item);
};

const updateAllItemLevelSalaries = (frm) => {
	(frm.doc.items || []).forEach((item) => updateItemLevelSalaries(frm, item));
};

frappe.ui.form.on("VNT Corporate Salary", {
	refresh(frm) {
		if (frm.is_new()) {
			if (!frm.doc.employee) {
				frappe.db
					.get_value("Employee", { user_id: frappe.session.user }, "name")
					.then((r) => r?.message?.name && frm.set_value("employee", r.message.name));
			}
			if (!frm.doc.date) {
				frm.set_value("date", frappe.datetime.now_date());
			}
		}

		updateAllItemLevelSalaries(frm);
	},
	corporate_minimum_wage(frm) {
		updateAllItemLevelSalaries(frm);
	},
	items_add(frm, cdt, cdn) {
		updateSalaryFieldsForEvent(frm, cdt, cdn);
	},
});

const corporateSalaryItemEvents = {};
LEVEL_SALARY_FIELDS.forEach(({ coefficient }) => {
	corporateSalaryItemEvents[coefficient] = function (frm, cdt, cdn) {
		updateSalaryFieldsForEvent(frm, cdt, cdn);
	};
});

frappe.ui.form.on("VNT Corporate Salary Item", corporateSalaryItemEvents);
