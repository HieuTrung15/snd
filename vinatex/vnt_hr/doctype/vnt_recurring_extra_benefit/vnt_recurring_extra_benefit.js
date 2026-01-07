// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

const VNT_RECURRING_TAX_RATE = 0.1;

frappe.ui.form.on("VNT Recurring Extra Benefit", {
	refresh(frm) {
		// Không yêu cầu hủy VNT Salary Slip khi hủy phiếu này
		frm.ignore_doctypes_on_cancel_all = ["VNT Salary Slip"];

		if (!frm.doc.employee) {
			frappe.db
				.get_value("Employee", { user_id: frappe.session.user }, "name")
				.then((r) => r?.message?.name && frm.set_value("employee", r.message.name));
		}
		if (!frm.doc.date) {
			frm.set_value("date", frappe.datetime.get_today());
		}
		if (!frm.doc.month) {
			frm.set_value("month", frappe.datetime.get_today().slice(5, 7));
		}
		if (!frm.doc.year) {
			frm.set_value("year", frappe.datetime.get_today().slice(0, 4));
		}

		vntRecurringSyncMonthToRows(frm);
		vntRecurringUpdateTotals(frm);
	},

	month(frm) {
		vntRecurringSyncMonthToRows(frm);
	},
	items_add(frm) {
		vntRecurringUpdateTotals(frm);
	},
	items_remove(frm) {
		vntRecurringUpdateTotals(frm);
	},

	get_emp_list(frm) {
		if (!frm.doc.type) {
			frappe.msgprint(__("Vui lòng chọn Loại phụ cấp trước."));
			return;
		}

		frm
			.call({
				doc: frm.doc,
				method: "get_emp_list",
				freeze: true,
				freeze_message: __("Đang lấy danh sách nhân sự..."),
			})
			.then((r) => {
				const payload = r?.message || {};
				const rows = Array.isArray(payload.items) ? payload.items : [];

				frm.clear_table("items");
				rows.forEach((item) => {
					if (!item.employee) return;
					const row = frm.add_child("items");
					row.employee = item.employee;
					row.designation = item.designation;
					row.allowance_type = item.allowance_type;
					row.he_so = item.he_so;
					row.amount = item.amount;
				});
				frm.refresh_field("items");
				vntRecurringSyncMonthToRows(frm);
				vntRecurringUpdateTotals(frm);

				if (!rows.length) {
					frappe.msgprint(
						__("Không tìm thấy nhân sự nào có loại phụ cấp đã chọn.")
					);
					return;
				}

				frappe.msgprint(
					__("Đã cập nhật danh sách cho {0} nhân sự.", [rows.length])
				);
			})
			.catch(() => {
				frappe.msgprint(
					__("Không thể lấy danh sách nhân sự. Vui lòng kiểm tra nhật ký.")
				);
		});
	},
});

frappe.ui.form.on("VNT Recurring Extra Benefit Item", {
	amount(frm, cdt, cdn) {
		vntRecurringRecalculateRow(cdt, cdn);
	},
	so_thang(frm, cdt, cdn) {
		vntRecurringRecalculateRow(cdt, cdn);
	},
	tong(frm) {
		vntRecurringUpdateTotals(frm);
	},
	thue_tncn(frm) {
		vntRecurringUpdateTotals(frm);
	},
	thuc_linh(frm) {
		vntRecurringUpdateTotals(frm);
	},
});

function vntRecurringNumber(value) {
	const num = parseFloat(value);
	return Number.isFinite(num) ? num : 0;
}

function vntRecurringUpdateTotals(frm) {
	if (!frm || !frm.doc) {
		return;
	}
	let totalAllowance = 0;
	let totalTax = 0;
	let totalNet = 0;

	(frm.doc.items || []).forEach((row) => {
		totalAllowance += vntRecurringNumber(row.tong);
		totalTax += vntRecurringNumber(row.thue_tncn);
		totalNet += vntRecurringNumber(row.thuc_linh);
	});

	frm.set_value("tong_pc", totalAllowance || 0);
	frm.set_value("tong_thue_tncn", totalTax || 0);
	frm.set_value("tong_thuc_linh", totalNet || 0);
}

function vntRecurringSyncMonthToRows(frm) {
	if (!frm || !frm.doc) {
		return;
	}
	const monthCount = vntRecurringCountMonths(frm.doc.month);
	const valueToSet = monthCount > 0 ? monthCount : null;
	(frm.doc.items || []).forEach((row) => {
		frappe.model.set_value(row.doctype, row.name, "so_thang", valueToSet);
	});
}

function vntRecurringRecalculateRow(cdt, cdn) {
	const row = locals?.[cdt]?.[cdn];
	if (!row) {
		return;
	}
	const months = Math.max(vntRecurringNumber(row.so_thang), 0);
	const amount = vntRecurringNumber(row.amount);
	const total = months * amount;
	const tax = total * VNT_RECURRING_TAX_RATE;
	const net = total - tax;

	frappe.model.set_value(cdt, cdn, "tong", total || 0);
	frappe.model.set_value(cdt, cdn, "thue_tncn", tax || 0);
	frappe.model.set_value(cdt, cdn, "thuc_linh", net || 0);

	if (cur_frm) {
		vntRecurringUpdateTotals(cur_frm);
	}
}

function vntRecurringCountMonths(value) {
	if (value === undefined || value === null) {
		return 0;
	}
	if (Array.isArray(value)) {
		return value.filter(Boolean).length;
	}
	const matches = String(value).match(/\d+/g) || [];
	const months = matches.filter((token) => {
		const num = parseInt(token, 10);
		return Number.isFinite(num) && num > 0 && num <= 12;
	});
	return months.length;
}
