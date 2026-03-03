// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

const VNT_T13_MONTH_FIELDS = [
	"t1",
	"t2",
	"t3",
	"t4",
	"t5",
	"t6",
	"t7",
	"t8",
	"t9",
	"t10",
	"t11",
	"t12",
];

const VNT_T13_FLOAT = (value) => {
	const num = parseFloat(value);
	return Number.isFinite(num) ? num : 0;
};

const VNT_T13_INT = (value) => {
	const num = parseInt(value, 10);
	return Number.isFinite(num) ? num : 0;
};

const VNT_T13_TOTAL_LABEL = __("Tổng lương đi làm năm");

const HR_SALARY_USERS = new Set([
	"tult@vinatex.com.vn",
	"hienht@vinatex.com.vn",
	"thaottt@vinatex.com.vn",
]);

frappe.ui.form.on("VNT 13th Month Salary", {
	refresh(frm) {
		enforceCreateRestriction(frm);
		if (frm.is_new() && !canManage13thMonthSalary()) {
			return;
		}

		// Lấy employee hiện tại nếu chưa có
		if (!frm.doc.employee) {
			frappe.db
				.get_value("Employee", { user_id: frappe.session.user }, "name")
				.then((r) => r?.message?.name && frm.set_value("employee", r.message.name));
		}
		if (!frm.doc.date) {
			frm.set_value("date", frappe.datetime.get_today());
		}
		if (!frm.doc.year) {
			frm.set_value("year", frappe.datetime.get_today().substr(0, 4));
		}
		updateTotalSalaryLabel(frm);
		if (frm.is_new()) {
			checkSubmitted13thSalary(frm);
		}
	},
	year(frm) {
		clearSalaryParamCache(frm);
		updateTotalSalaryLabel(frm);
		if (frm.is_new()) {
			checkSubmitted13thSalary(frm);
		}
	},
	luong_thang(frm) {
		updateTotalSalaryLabel(frm);
		if (frm.is_new()) {
			checkSubmitted13thSalary(frm);
		}
	},
	company(frm) {
		if (frm.is_new()) {
			checkSubmitted13thSalary(frm);
		}
	},
	branch(frm) {
		if (frm.is_new()) {
			checkSubmitted13thSalary(frm);
		}
	},

	get_emp_list(frm) {
		// if (frm.doc.luong_thang !== "T13") {
		// 	// frappe.msgprint(__("Chỉ được lấy dữ liệu khi loại lương là T13."));
		// 	return;
		// }
		if (!frm.doc.company) {
			frappe.msgprint(__("Vui lòng chọn Công ty trước khi lấy danh sách nhân sự."));
			return;
		}
		if (!frm.doc.branch) {
			frappe.msgprint(__("Vui lòng chọn Chi nhánh trước khi lấy danh sách nhân sự."));
			return;
		}
		if (!frm.doc.year) {
			frappe.msgprint(__("Vui lòng nhập Năm trước khi lấy danh sách nhân sự."));
			return;
		}

		let progressTimer;

		const showProgress = () => {
			frappe.show_progress(
				__("Đang tổng hợp dữ liệu tháng 13"),
				0,
				100,
				__("Vui lòng đợi, hệ thống đang tính toán...")
			);
			progressTimer = setTimeout(() => {}, 0); // giữ tham chiếu để clear
		};

		const hideProgress = () => {
			if (progressTimer) {
				clearTimeout(progressTimer);
				progressTimer = null;
			}
			frappe.hide_progress && frappe.hide_progress();
		};

		showProgress();

		return frm
			.call({
				doc: frm.doc,
				method: "get_emp_list",
				freeze: true,
				freeze_message: __("Đang lấy dữ liệu thực lĩnh từng tháng..."),
			})
			.then((r) => {
				const payload = r?.message || {};
				const rows = Array.isArray(payload.items) ? payload.items : [];
				const total = rows.length || 1;
				let processed = 0;

				frm.clear_table("items");
				rows.forEach((item) => {
					if (!item.employee) return;
					const row = frm.add_child("items");
					frappe.model.set_value(row.doctype, row.name, "employee", item.employee);

					VNT_T13_MONTH_FIELDS.forEach((field) => {
						row[field] = item[field] ?? null;
					});

					if (Object.prototype.hasOwnProperty.call(item, "tong_luong_di_lam")) {
						row.tong_luong_di_lam = item.tong_luong_di_lam;
					}
					if (Object.prototype.hasOwnProperty.call(item, "binh_quan_thang")) {
						row.binh_quan_thang = item.binh_quan_thang;
					}

					processed++;
					frappe.show_progress(
						__("Đang tổng hợp dữ liệu tháng 13"),
						Math.min((processed / total) * 100, 100),
						100,
						__("Đang xử lý: {0}/{1}", [processed, total])
					);
				});

				frm.refresh_field("items");

				if (!rows.length) {
					frappe.msgprint(
						__("Không tìm thấy nhân sự Active thuộc Công ty/Chi nhánh đã chọn.")
					);
					return;
				}

				const monthCount = Array.isArray(payload.sourced_months)
					? payload.sourced_months.length
					: 0;
				const msg =
					monthCount > 0
						? __("Đã cập nhật {0} nhân sự với dữ liệu của {1} tháng.", [
								rows.length,
								monthCount,
							])
						: __(
								"Đã cập nhật {0} nhân sự nhưng chưa tìm thấy bảng lương nào cho năm {1}.",
								[rows.length, frm.doc.year]
							);
				frappe.msgprint(msg);
			})
			.catch((err) => {
				console.error(err);
				frappe.msgprint(__("Không thể lấy dữ liệu nhân sự. Vui lòng xem nhật ký trình duyệt."));
			})
			.finally(() => {
				hideProgress();
			});
	},
});

frappe.ui.form.on("VNT 13th Month Salary Item", {
	he_so(frm, cdt, cdn) {
		const amount = updateSupplementSalary(cdt, cdn);
		updateTaxableIncome(frm, cdt, cdn, amount);
	},
	xep_loai(frm, cdt, cdn) {
		const amount = updateSupplementSalary(cdt, cdn);
		updateTaxableIncome(frm, cdt, cdn, amount);
	},
	nguoi_phu_thuoc(frm, cdt, cdn) {
		updateTaxableIncome(frm, cdt, cdn);
	},
	tien_luong_bo_sung(frm, cdt, cdn) {
		updateTaxableIncome(frm, cdt, cdn);
	},
	truy_linh(frm, cdt, cdn) {
		updateTaxableIncome(frm, cdt, cdn);
	},
});

function enforceCreateRestriction(frm) {
	if (!frm.is_new()) return;

	if (canManage13thMonthSalary()) return;

	frm.disable_save();
	frm.set_intro(__("Bạn không có quyền tạo mới chứng từ này. Liên hệ HR lương."), "red");
	if (frm.page && frm.page.set_primary_action) {
		frm.page.clear_primary_action && frm.page.clear_primary_action();
	}
}

function canManage13thMonthSalary() {
	const user = frappe.session?.user;
	if (!user || user === "Guest") return false;
	if (user === "Administrator") return true;
	return HR_SALARY_USERS.has(user);
}

function updateSupplementSalary(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row) return 0;

	const avg = VNT_T13_FLOAT(row.binh_quan_thang);
	const coef = VNT_T13_FLOAT(row.he_so);
	const amount = avg * coef;

	frappe.model.set_value(cdt, cdn, "tien_luong_bo_sung", amount);
	return amount;
}

function updateTaxableIncome(frm, cdt, cdn, overrideSalary) {
	const row = locals[cdt][cdn];
	if (!row) return;

	const salary =
		typeof overrideSalary === "number" ? overrideSalary : VNT_T13_FLOAT(row.tien_luong_bo_sung);
	const bonus = VNT_T13_FLOAT(row.truy_linh);
	const salaryWithBonus = salary + bonus;
	const dependents = VNT_T13_INT(row.nguoi_phu_thuoc);

	if (!salaryWithBonus || !frm.doc.year) {
		frappe.model.set_value(cdt, cdn, "thu_nhap_tinh_thue", null);
		frappe.model.set_value(cdt, cdn, "thue_tam_thu", null);
		frappe.model.set_value(cdt, cdn, "thu_nhap_thuc_linh", null);
		return;
	}

	ensureSalaryParameter(frm)
		.then((param) => {
			if (!param) return;
			const personalDeduction = VNT_T13_FLOAT(param.giam_tru_gia_canh);
			const dependentDeduction = VNT_T13_FLOAT(param.giam_tru_npt) * dependents;
			const taxable = Math.max(0, salaryWithBonus - personalDeduction - dependentDeduction);
			frappe.model.set_value(cdt, cdn, "thu_nhap_tinh_thue", taxable || null);

			if (!taxable) {
				frappe.model.set_value(cdt, cdn, "thue_tam_thu", null);
				frappe.model.set_value(cdt, cdn, "thu_nhap_thuc_linh", salaryWithBonus || null);
				return;
			}

			const tax = calculateProgressiveTax(taxable, param.tax_brackets);
			frappe.model.set_value(cdt, cdn, "thue_tam_thu", tax || null);
			const netIncome = salaryWithBonus - (tax || 0);
			frappe.model.set_value(cdt, cdn, "thu_nhap_thuc_linh", netIncome || null);
		})
		.catch((err) => {
			console.error(err);
			frappe.msgprint(
				__(
					"Không thể lấy Tham số lương để tính thu nhập tính thuế. Vui lòng kiểm tra lại cấu hình."
				)
			);
		});
}

function ensureSalaryParameter(frm) {
	const year = VNT_T13_INT(frm.doc.year);
	if (!year) {
		return Promise.resolve(null);
	}

	if (frm._vnt_salary_param && frm._vnt_salary_param_year === year) {
		return Promise.resolve(frm._vnt_salary_param);
	}

	return frappe
		.call({
			method:
				"vinatex.vnt_hr.doctype.vnt_13th_month_salary.vnt_13th_month_salary.get_salary_parameter_for_year",
			args: { year },
		})
		.then((r) => {
			const param = r?.message || null;
			frm._vnt_salary_param = param;
			frm._vnt_salary_param_year = year;
			return param;
		});
}

function clearSalaryParamCache(frm) {
	frm._vnt_salary_param = null;
	frm._vnt_salary_param_year = null;
}

function updateTotalSalaryLabel(frm) {
	const grid = frm.fields_dict?.items?.grid;
	if (!grid) return;

	let label = VNT_T13_TOTAL_LABEL;
	if (frm.doc.luong_thang === "T13" && frm.doc.year) {
		label = `${VNT_T13_TOTAL_LABEL} ${frm.doc.year}`;
	}

	grid.update_docfield_property("tong_luong_di_lam", "label", label);
	grid.refresh();
}

function calculateProgressiveTax(amount, brackets = []) {
	if (!amount || !Array.isArray(brackets) || !brackets.length) return 0;

	const sorted = [...brackets].sort(
		(a, b) => VNT_T13_FLOAT(a.from) - VNT_T13_FLOAT(b.from)
	);

	let tax = 0;
	let processedUpper = 0;

	for (const bracket of sorted) {
		const rate = VNT_T13_FLOAT(bracket.percent) / 100;
		const start = Math.max(VNT_T13_FLOAT(bracket.from), processedUpper);
		const rawEnd = bracket.to === null || typeof bracket.to === "undefined" ? null : VNT_T13_FLOAT(bracket.to);
		const end = rawEnd === null ? null : Math.max(rawEnd, start);

		if (amount <= start) {
			break;
		}

		const effectiveEnd = end === null ? amount : Math.min(end, amount);
		const chunk = Math.max(0, effectiveEnd - start);
		if (chunk > 0 && rate > 0) {
			tax += chunk * rate;
		}

		processedUpper = end === null ? amount : end;

		if (amount <= processedUpper) {
			break;
		}
	}

	return tax;
}

function checkSubmitted13thSalary(frm) {
	const args = {
		luong_thang: frm.doc.luong_thang,
		year: frm.doc.year,
		company: frm.doc.company,
		branch: frm.doc.branch,
	};

	if (!args.luong_thang || !args.year) {
		return;
	}

	const key = `${args.luong_thang}-${args.year}-${args.company || ""}-${args.branch || ""}`;
	if (frm._vnt_dup_warned && frm._vnt_dup_key === key) {
		return;
	}
	if (frm._vnt_dup_pending === key) {
		return;
	}
	frm._vnt_dup_pending = key;

	frappe.call({
		method: "vinatex.vnt_hr.doctype.vnt_13th_month_salary.vnt_13th_month_salary.has_submitted_13th_salary",
		args,
		callback: (r) => {
			if (r?.message) {
				if (!frm._vnt_dup_warned || frm._vnt_dup_key !== key) {
					frm._vnt_dup_warned = true;
					frm._vnt_dup_key = key;
					frappe.msgprint(__("Đã tồn tại bảng lương {0} năm {1} đã xác nhận cho đơn vị này. Vui lòng kiểm tra lại.", [args.luong_thang, args.year]));
				}
			}
			frm._vnt_dup_pending = null;
		},
		always: () => {
			if (frm._vnt_dup_pending === key) {
				frm._vnt_dup_pending = null;
			}
		}
	});
}
