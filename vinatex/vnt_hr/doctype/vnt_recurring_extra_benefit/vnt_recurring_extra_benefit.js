// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Recurring Extra Benefit", {
	refresh(frm) {
		// Không yêu cầu hủy VNT Salary Slip khi hủy phiếu này
		frm.ignore_doctypes_on_cancel_all = ["VNT Salary Slip"];

		if (frm.is_new()) {
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
		}

		const allowanceTypeKey = vntRecurringNormalizeType(frm.doc.type);
		if (["PC DAC THU", "PC DT"].includes(allowanceTypeKey) && !frm.doc.luong_tt) {
			vntRecurringApplyAllowanceType(frm);
		}
	},

	month(frm) {
		vntRecurringSyncMonthToRows(frm);
	},
	type(frm) {
		vntRecurringApplyAllowanceType(frm);
	},
	luong_tt(frm) {
		vntRecurringRecalculateAllRows(frm);
	},
	items_add(frm) {
		vntRecurringUpdateTotals(frm);
	},
	items_remove(frm) {
		vntRecurringUpdateTotals(frm);
	},
	excel(frm) {
		vntRecurringDownloadExcel(frm);
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
				const allowanceTypeKey = vntRecurringNormalizeType(frm.doc.type);
				const isDacThu = ["PC DAC THU", "PC DT"].includes(allowanceTypeKey);
				if (isDacThu && payload.luong_tt) {
					frm.set_value("luong_tt", vntRecurringNumber(payload.luong_tt));
				}

				frm.clear_table("items");
				rows.forEach((item) => {
					if (!item.employee) return;
					const row = frm.add_child("items");
					row.employee = item.employee;
					row.designation = item.designation;
					row.allowance_type = item.allowance_type;
					row.he_so = item.he_so;
					row.amount = item.amount;
					row.thue = item.thue;
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
	thue(frm, cdt, cdn) {
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

	vntRecurringSetParentIfChanged(frm, "tong_pc", totalAllowance || 0);
	vntRecurringSetParentIfChanged(frm, "tong_thue_tncn", totalTax || 0);
	vntRecurringSetParentIfChanged(frm, "tong_thuc_linh", totalNet || 0);
}

function vntRecurringSyncMonthToRows(frm, options = {}) {
	if (!frm || !frm.doc) {
		return;
	}
	if (options.skipIfSaved && !frm.is_new()) {
		return;
	}
	const monthCount = vntRecurringCountMonths(frm.doc.month);
	const valueToSet = monthCount > 0 ? monthCount : null;
	(frm.doc.items || []).forEach((row) => {
		const currentRaw = row.so_thang;
		const currentValue =
			currentRaw === null || currentRaw === undefined || currentRaw === ""
				? null
				: parseInt(currentRaw, 10);
		if (currentValue === valueToSet) {
			return;
		}
		frappe.model.set_value(row.doctype, row.name, "so_thang", valueToSet);
	});
}

function vntRecurringSetParentIfChanged(frm, fieldname, value) {
	if (!frm || !frm.doc) {
		return;
	}
	const current = vntRecurringNumber(frm.doc[fieldname]);
	const target = vntRecurringNumber(value);
	if (Math.abs(current - target) < 0.000001) {
		return;
	}
	frm.set_value(fieldname, target);
}

function vntRecurringRecalculateRow(cdt, cdn) {
	const row = locals?.[cdt]?.[cdn];
	if (!row) {
		return;
	}
	const months = Math.max(vntRecurringNumber(row.so_thang), 0);
	let amount = vntRecurringNumber(row.amount);
	const allowanceTypeKey = vntRecurringNormalizeType(cur_frm?.doc?.type);
	if (["PC DAC THU", "PC DT"].includes(allowanceTypeKey)) {
		amount = vntRecurringNumber(cur_frm?.doc?.luong_tt) * vntRecurringNumber(row.he_so);
		row.amount = amount;
	}
	const total = months * amount;
	const taxRate = Math.min(Math.max(vntRecurringNumber(row.thue), 0), 100) / 100;
	const tax = total * taxRate;
	const net = total - tax;

	frappe.model.set_value(cdt, cdn, "tong", total || 0);
	frappe.model.set_value(cdt, cdn, "thue_tncn", tax || 0);
	frappe.model.set_value(cdt, cdn, "thuc_linh", net || 0);

	if (cur_frm) {
		vntRecurringUpdateTotals(cur_frm);
	}
}

function vntRecurringRecalculateAllRows(frm) {
	if (!frm || !frm.doc) {
		return;
	}
	(frm.doc.items || []).forEach((row) => {
		vntRecurringRecalculateRow(row.doctype, row.name);
	});
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

function vntRecurringDownloadExcel(frm) {
	if (!frm || !frm.doc) {
		return;
	}
	if (frm.is_new() || !frm.doc.name) {
		frappe.msgprint(__("Vui lòng lưu chứng từ trước khi tải xuống Excel."));
		return;
	}
	if (frm.is_dirty()) {
		frappe.msgprint(__("Vui lòng lưu chứng từ trước khi tải xuống Excel."));
		return;
	}
	const allowanceTypeKey = vntRecurringNormalizeType(frm.doc.type);
	if (!["PC CDS", "PC BAN CHQS", "PC CHQS", "PC DAC THU", "PC DT"].includes(allowanceTypeKey)) {
		frappe.msgprint(
			__('Hiện chỉ hỗ trợ tải Excel cho "Loại phụ cấp" là PC CĐS, PC Ban CHQS hoặc PC đặc thù.')
		);
		return;
	}

	const method =
		"vinatex.vnt_hr.doctype.vnt_recurring_extra_benefit.vnt_recurring_extra_benefit.download_recurring_extra_benefit_excel";
	const params = new URLSearchParams({
		docname: frm.doc.name,
	});
	const url = `/api/method/${method}?${params.toString()}`;
	const fullUrl = frappe.urllib.get_full_url(url);
	window.open(fullUrl);
}

function vntRecurringApplyAllowanceType(frm) {
	if (!frm || !frm.doc) {
		return;
	}

	const allowanceTypeKey = vntRecurringNormalizeType(frm.doc.type);
	const isDacThu = ["PC DAC THU", "PC DT"].includes(allowanceTypeKey);
	frm.toggle_display("luong_tt", isDacThu);
	frm.toggle_reqd("luong_tt", isDacThu);
	if (!isDacThu) {
		if (frm.doc.luong_tt) {
			frm.set_value("luong_tt", null);
		}
		return;
	}

	frm.call({
		doc: frm.doc,
		method: "fetch_luong_tt",
		freeze: false,
	}).then((r) => {
		const payload = r?.message || {};
		const luongTT = vntRecurringNumber(payload.corporate_minimum_wage || 0);
		frm.set_value("luong_tt", luongTT || null);
		if (!luongTT) {
			frappe.msgprint(__("Không tìm thấy VNT Salary Parameter (đã Submit) còn hiệu lực."));
		}
	}).catch(() => {
		frappe.msgprint(__("Không lấy được Lương TT từ VNT Salary Parameter."));
	});
}

function vntRecurringNormalizeType(value) {
	const raw = (value || "").toString().trim().toUpperCase();
	if (!raw) {
		return "";
	}
	return raw
		.normalize("NFD")
		.replace(/[\u0300-\u036f]/g, "")
		.replace(/Đ/g, "D")
		.replace(/\s+/g, " ");
}
