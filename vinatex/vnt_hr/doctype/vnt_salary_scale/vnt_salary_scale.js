// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

const LEVEL_SALARY_FIELDS = Array.from({ length: 10 }, (_, index) => ({
	coefficient: `${index + 1}`,
	salary: `ml_b${index + 1}`,
}));

const updateItemLevelSalaries = (frm, item) => {
	if (!item) {
		return;
	}

	const baseSalary = frappe.utils.flt(frm.doc.regional_minimum_wage);

	LEVEL_SALARY_FIELDS.forEach(({ coefficient, salary }) => {
		const coefficientValue = frappe.utils.flt(item[coefficient]);
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

frappe.ui.form.on("VNT Salary Scale", {
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
	regional_minimum_wage(frm) {
		updateAllItemLevelSalaries(frm);
	},
	items_add(frm, cdt, cdn) {
		updateSalaryFieldsForEvent(frm, cdt, cdn);
	},
});

const salaryScaleItemEvents = {};
LEVEL_SALARY_FIELDS.forEach(({ coefficient }) => {
	salaryScaleItemEvents[coefficient] = function (frm, cdt, cdn) {
		updateSalaryFieldsForEvent(frm, cdt, cdn);
	};
});

frappe.ui.form.on("VNT Salary Scale Item", salaryScaleItemEvents);
