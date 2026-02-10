// Copyright (c) 2026, vinatex and contributors
// For license information, please see license.txt

const syncDepartmentFromEmployee = (frm, override = false) => {
	if (!frm.doc.employee) {
		if (override && frm.doc.department) {
			frm.set_value("department", "");
		}
		return Promise.resolve();
	}

	return frappe.db.get_value("Employee", frm.doc.employee, "department").then((r) => {
		const employeeDept = (r.message && r.message.department) || "";
		if (!employeeDept) {
			return;
		}
		if (override || !frm.doc.department) {
			frm.set_value("department", employeeDept);
		}
	});
};

frappe.ui.form.on("VNT Task", {
	refresh(frm) {
		if (frm.doc.employee && !frm.doc.department) {
			syncDepartmentFromEmployee(frm);
		}
	},
	employee(frm) {
		syncDepartmentFromEmployee(frm, true);
	},
	kpi_cv_item(frm) {
		if (!frm.doc.kpi_cv_item) {
			return;
		}

		frappe.db
			.get_value(
				"VNT KPI Chuyen Vien Item",
				frm.doc.kpi_cv_item,
				["kpi_details", "date", "parent"],
			)
			.then((r) => {
				const data = r.message || {};

				if (!frm.doc.congviec && data.kpi_details) {
					frm.set_value("congviec", data.kpi_details);
				}
				if (!frm.doc.deadline && data.date) {
					frm.set_value("deadline", data.date);
				}

				if (!data.parent) {
					return;
				}

				return frappe.db.get_value(
					"VNT KPI Chuyen Vien",
					data.parent,
					["emp_chuyenvien", "department"],
				);
			})
			.then((parentResp) => {
				const parent = (parentResp && parentResp.message) || {};
				if (!frm.doc.employee && parent.emp_chuyenvien) {
					frm.set_value("employee", parent.emp_chuyenvien);
				}
				if (!frm.doc.department && parent.department) {
					frm.set_value("department", parent.department);
				}
			});
	},
});
