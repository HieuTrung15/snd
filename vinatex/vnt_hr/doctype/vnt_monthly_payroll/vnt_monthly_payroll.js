// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Monthly Payroll", {
	
    refresh(frm) {
		if (!canManagePayroll()) {
			if (frm.is_new()) {
				frappe.msgprint(__("Bạn không được phép tạo bảng lương. Vui lòng liên hệ HR."));
				frappe.set_route("List", "VNT Monthly Payroll");
				return;
			}
		}

        if (!frm.doc.month || !frm.doc.year) {
            frm.set_value("month", frappe.datetime.get_today().substr(5, 2));
            frm.set_value("year", frappe.datetime.get_today().substr(0, 4));
        }
        if (!frm.doc.employee) {
            frappe.db.get_value("Employee", { user_id: frappe.session.user }, "name")
            .then(r => r?.message?.name && frm.set_value("employee", r.message.name));
        }
        if (!frm.doc.date) {
            frm.set_value("date", frappe.datetime.now_date());
        }
        if (frm.doc.month && frm.doc.year) {
            const month = parseInt(frm.doc.month, 10);
            const year = parseInt(frm.doc.year, 10);
            get_standard_working_days(frm, month, year);
        }
        add_download_button(frm);


		if (frm.is_new()) {
			check_submitted_payroll_exists(frm);
		}

    },
    month (frm) {
        if (frm.doc.month && frm.doc.year) {
            const month = parseInt(frm.doc.month, 10);
            const year = parseInt(frm.doc.year, 10);
            get_standard_working_days(frm, month, year);
        }
		if (frm.is_new()) {
			check_submitted_payroll_exists(frm);
		}
    },
    year (frm) {
        if (frm.doc.month && frm.doc.year) {
            const month = parseInt(frm.doc.month, 10);
            const year = parseInt(frm.doc.year, 10);
            get_standard_working_days(frm, month, year);
        }
		if (frm.is_new()) {
			check_submitted_payroll_exists(frm);
		}
    },
	get_salary(frm) {
		if (!canManagePayroll()) {
			frappe.msgprint(__("Bạn không được phép tính lương. Vui lòng liên hệ HR."));
			return;
		}

		if (!frm.doc.company) {
			frappe.msgprint(__("Vui lòng chọn Công ty trước khi lấy danh sách nhân sự."));
			return;
		}

		const args = { company: frm.doc.company };
		if (frm.doc.branch) {
			args.branch = frm.doc.branch;
		}

		frappe
			.call({
				method:
					"vinatex.vnt_hr.doctype.vnt_monthly_payroll.vnt_monthly_payroll.get_active_employees",
				args,
				freeze: true,
				freeze_message: __("Đang lấy danh sách nhân sự..."),
			})
			.then((r) => {
				const employees = Array.isArray(r?.message) ? r.message : [];
				if (!employees.length) {
					frappe.msgprint(__("Không tìm thấy nhân sự phù hợp điều kiện đã chọn."));
					return save_then_compute(frm, { notify_no_new: false });
				}

				const existing = new Set(
					(frm.doc.items || [])
						.map((row) => row.employee)
						.filter((employee) => !!employee)
				);

				let added = 0;
				frm._vnt_skip_employee_compute = true;
				try {
					for (const emp of employees) {
						if (existing.has(emp.name)) continue;

						const row = frm.add_child("items");
						frappe.model.set_value(row.doctype, row.name, "employee", emp.name);

						if (emp.employment_type) {
							frappe.model.set_value(
								row.doctype,
								row.name,
								"employement_type",
								emp.employment_type
							);
						}
						if (emp.custom_party_member) {
							frappe.model.set_value(
								row.doctype,
								row.name,
								"dang_vien",
								emp.custom_party_member
							);
						}
						if (typeof emp.custom_relation_number !== "undefined") {
							frappe.model.set_value(
								row.doctype,
								row.name,
								"so_npt",
								emp.custom_relation_number
							);
						}

						added++;
						existing.add(emp.name);
					}
				} finally {
					frm._vnt_skip_employee_compute = false;
				}

				frm.refresh_field("items");
				return save_then_compute(frm, {
					added_count: added,
					notify_no_new: true,
				});
			});
	},

	compute_row(frm, row, opts = {}) {
		if (!canManagePayroll()) {
			if (!frm._vnt_payroll_permission_warned) {
				frappe.msgprint(__("Bạn không được phép tính lương. Vui lòng liên hệ HR."));
				frm._vnt_payroll_permission_warned = true;
			}
			return Promise.resolve();
		}
		if (!row || !row.employee) return Promise.resolve();

		const args = {
			employee: row.employee,
			company: frm.doc.company,
			month: frm.doc.month,
			year: frm.doc.year,
		};
		const freeze = opts.freeze !== false;
		const refresh = opts.refresh !== false;

		return frappe
			.call({
				method:
					"vinatex.vnt_hr.doctype.vnt_monthly_payroll.vnt_monthly_payroll.compute_item",
				args,
				freeze,
				freeze_message: __("Đang tính lương cho nhân sự..."),
			})
			.then((r) => {
				if (!r || !r.message) return;

				applyPayrollPayload(frm, row, r.message, { refresh });
			});
	},
});

frappe.ui.form.on("VNT Monthly Payroll Item", {
	employee(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (frm._vnt_skip_employee_compute) {
			return;
		}
		frm.events.compute_row(frm, row);
	},
	truylinh(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row || !row.employee) return;
		if (row._current_payroll_payload) {
			applyPayrollPayload(frm, row, row._current_payroll_payload);
			return;
		}
		if (!frm.doc.month || !frm.doc.year) return;
		frm.events.compute_row(frm, row, { freeze: false });
	},
	cho_phep_dong_bhxh(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row || !row.employee) return;
		if (row._current_payroll_payload) {
			applyPayrollPayload(frm, row, row._current_payroll_payload);
			return;
		}
		if (!frm.doc.month || !frm.doc.year) return;
		frm.events.compute_row(frm, row, { freeze: false });
	},
	khac(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row || !row.employee) return;
		if (row._current_payroll_payload) {
			applyPayrollPayload(frm, row, row._current_payroll_payload);
			return;
		}
		if (!frm.doc.month || !frm.doc.year) return;
		frm.events.compute_row(frm, row, { freeze: false });
	},
	truy_thu(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row || !row.employee) return;
		if (row._current_payroll_payload) {
			applyPayrollPayload(frm, row, row._current_payroll_payload);
			return;
		}
		if (!frm.doc.month || !frm.doc.year) return;
		frm.events.compute_row(frm, row, { freeze: false });
	},
	duoc_hoan_lai(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row || !row.employee) return;
		if (row._current_payroll_payload) {
			applyPayrollPayload(frm, row, row._current_payroll_payload);
			return;
		}
		if (!frm.doc.month || !frm.doc.year) return;
		frm.events.compute_row(frm, row, { freeze: false });
	},
});

function check_submitted_payroll_exists(frm) {
	if (!frm.doc.month || !frm.doc.year) {
		return;
	}

	frappe.call({
		method: "vinatex.vnt_hr.doctype.vnt_monthly_payroll.vnt_monthly_payroll.has_submitted_payroll",
		args: {
			month: frm.doc.month,
			year: frm.doc.year,
		},
		callback: (r) => {
			if (r?.message) {
				frappe.msgprint(__("Đã tồn tại phiếu lương cho tháng và năm đã chọn với trạng thái 'Đã xác nhận'. Vui lòng kiểm tra lại."));
			}
		},
	});
}

function add_download_button(frm) {
	if (frm.is_new() || !frm.doc.name) {
		return;
	}

	frm.add_custom_button(__("Tải xuống Excel"), () => {
		if (!frm.doc.type_doc) {
			frappe.msgprint(__("Vui lòng chọn \"Loại biểu mẫu\" trước khi tải xuống."));
			return;
		}
		const supportedTypes = ["Biểu mẫu Bảng tổng", "Biểu mẫu DS chi", "Biểu mẫu BL tháng"];
		if (!supportedTypes.includes(frm.doc.type_doc)) {
			frappe.msgprint(
				__("Loại biểu mẫu này hiện chưa hỗ trợ tải xuống. Vui lòng chọn một trong: {0}", [
					supportedTypes.join(", "),
				])
			);
			return;
		}

		const method =
			"vinatex.vnt_hr.doctype.vnt_monthly_payroll.vnt_monthly_payroll.download_payroll_excel";
		const params = new URLSearchParams({
			docname: frm.doc.name,
			type_doc: frm.doc.type_doc,
		});
		const url = `/api/method/${method}?${params.toString()}`;
		const fullUrl = frappe.urllib.get_full_url(url);
		window.open(fullUrl);
	});
}


// ===== HÀM DỊCH VỤ: số ngày công tiêu chuẩn (không T7-CN) =====
function get_standard_working_days(frm, month, year) {
    if (!frm || Number.isNaN(month) || Number.isNaN(year)) return;
    const daysInMonth = new Date(year, month, 0).getDate();
    let workingDays = 0;
    for (let day = 1; day <= daysInMonth; day++) {
        const date = new Date(year, month - 1, day);
        const dow = date.getDay();          // 0: CN, 6: T7
        if (dow !== 0 && dow !== 6) workingDays++;
    }
    frm.set_value("standard_working_days", workingDays);
    frm.refresh_field("standard_working_days");
}

function save_then_compute(frm, opts = {}) {
	const { added_count = 0, notify_no_new = false } = opts || {};

	return frm
		.save()
		.then(() => run_salary_compute(frm, { added_count, notify_no_new }))
		.catch((err) => {
			console.error(err);
			frappe.msgprint(
				__("Không thể lưu chứng từ trước khi tính lương. Vui lòng kiểm tra dữ liệu và thử lại.")
			);
			throw err;
		});
}

function run_salary_compute(frm, opts = {}) {
	const { added_count = 0, notify_no_new = false } = opts || {};
	const rowsToCompute = (frm.doc.items || []).filter((item) => item && item.employee);

	if (!rowsToCompute.length) {
		if (notify_no_new && added_count === 0) {
			frappe.msgprint(__("Tất cả nhân sự đã có trong bảng lương."));
		}
		return Promise.resolve();
	}

	frappe.dom.freeze(__("Đang tính lương, vui lòng đợi..."));
	return compute_all_items(frm, rowsToCompute)
		.catch((err) => {
			console.error(err);
			frappe.msgprint(
				__("Có lỗi xảy ra khi tính lương. Vui lòng kiểm tra nhật ký trình duyệt.")
			);
		})
		.finally(() => {
			frappe.dom.unfreeze();
			frm.refresh_field("items");
			if (notify_no_new && added_count === 0) {
				frappe.msgprint(__("Tất cả nhân sự đã có trong bảng lương."));
			}
		});
}

function applyPayrollPayload(frm, row, payload, opts = {}) {
	if (!row || !payload) return;
	const refresh = opts && Object.prototype.hasOwnProperty.call(opts, "refresh") ? opts.refresh !== false : true;

	row._current_payroll_payload = payload;

	const currentContractType = payload.current_contract_type || "";
	const previousContractType = payload.previous_contract_type || "";
	const previousWorkingDays = toNumber(payload.previous_working_days || 0);
	const currentWorkingDays = toNumber(
		typeof payload.current_working_days !== "undefined" && payload.current_working_days !== null
			? payload.current_working_days
			: payload.ngaycong
	);
	const hasCurrentCoefficient =
		typeof payload.current_salary_coefficient !== "undefined" &&
		payload.current_salary_coefficient !== null;
	const hasPreviousCoefficient =
		typeof payload.previous_salary_coefficient !== "undefined" &&
		payload.previous_salary_coefficient !== null;
	const latestSalaryCoefficient =
		typeof payload.latest_salary_coefficient !== "undefined" &&
		payload.latest_salary_coefficient !== null
			? toNumber(payload.latest_salary_coefficient)
			: null;
	const hasCurrentSalaryAmount =
		typeof payload.current_salary_amount !== "undefined" &&
		payload.current_salary_amount !== null;
	const hasPreviousSalaryAmount =
		typeof payload.previous_salary_amount !== "undefined" &&
		payload.previous_salary_amount !== null;
	const latestSalaryAmount =
		typeof payload.latest_salary_amount !== "undefined" &&
		payload.latest_salary_amount !== null
			? toNumber(payload.latest_salary_amount)
			: null;

	let heSoCbnv = hasCurrentCoefficient
		? toNumber(payload.current_salary_coefficient)
		: latestSalaryCoefficient !== null
			? latestSalaryCoefficient
			: toNumber(row.he_so_cbnv);
	if (hasCurrentCoefficient) {
		frappe.model.set_value(row.doctype, row.name, "he_so_cbnv", heSoCbnv);
	}
	row.he_so_cbnv = heSoCbnv;

	if (hasCurrentSalaryAmount || latestSalaryAmount !== null) {
		const mucLuongHqcv = hasCurrentSalaryAmount
			? toNumber(payload.current_salary_amount)
			: latestSalaryAmount !== null
				? latestSalaryAmount
				: toNumber(row.muc_luong_theo_hqcv);
		frappe.model.set_value(row.doctype, row.name, "muc_luong_theo_hqcv", mucLuongHqcv);
		row.muc_luong_theo_hqcv = mucLuongHqcv;
	}

	let heSoCbnvCu = hasPreviousCoefficient
		? toNumber(payload.previous_salary_coefficient)
		: toNumber(row.he_so_cbnv_cu);
	if (previousWorkingDays > 0) {
		if (hasPreviousCoefficient) {
			row.he_so_cbnv_cu = heSoCbnvCu;
			frappe.model.set_value(row.doctype, row.name, "he_so_cbnv_cu", heSoCbnvCu);
		} else {
			row.he_so_cbnv_cu = "";
			frappe.model.set_value(row.doctype, row.name, "he_so_cbnv_cu", "");
		}
	} else {
		row.he_so_cbnv_cu = "";
		frappe.model.set_value(row.doctype, row.name, "he_so_cbnv_cu", "");
	}

	if (previousWorkingDays > 0) {
		if (hasPreviousSalaryAmount) {
			const mucLuongHqcvCu = toNumber(payload.previous_salary_amount);
			row.muc_luong_theo_hqcv_cu = mucLuongHqcvCu;
			frappe.model.set_value(
				row.doctype,
				row.name,
				"muc_luong_theo_hqcv_cu",
				mucLuongHqcvCu
			);
		} else {
			row.muc_luong_theo_hqcv_cu = "";
			frappe.model.set_value(row.doctype, row.name, "muc_luong_theo_hqcv_cu", "");
		}
	} else {
		row.muc_luong_theo_hqcv_cu = "";
		frappe.model.set_value(row.doctype, row.name, "muc_luong_theo_hqcv_cu", "");
	}

	row.employement_type = currentContractType;
	frappe.model.set_value(row.doctype, row.name, "employement_type", currentContractType);
	row.employement_type_cur = previousContractType;
	frappe.model.set_value(row.doctype, row.name, "employement_type_cur", previousContractType);

	row.ngay_cong = currentWorkingDays;
	row.ngay_cong_cu = previousWorkingDays;
	frappe.model.set_value(row.doctype, row.name, "ngay_cong", currentWorkingDays);
	frappe.model.set_value(row.doctype, row.name, "ngay_cong_cu", previousWorkingDays);

	const regionalMinWage = toNumber(payload.regional_minimum_wage);
	const corporateMinWage = toNumber(payload.corporate_minimum_wage);

	frappe.model.set_value(
		row.doctype,
		row.name,
		"luong_cb",
		regionalMinWage * toNumber(row.hs_luong_cb)
	);
	frappe.model.set_value(
		row.doctype,
		row.name,
		"pc_dang1",
		regionalMinWage * toNumber(row.hs_pc_dang_1)
	);
	frappe.model.set_value(
		row.doctype,
		row.name,
		"pc_kiem_nhiem1",
		regionalMinWage * toNumber(row.hs_pc_kiem_nhiem1)
	);

	const luongCb = toNumber(row.luong_cb);
	const pcDang1 = toNumber(row.pc_dang1);
	const pcKiemNhiem1 = toNumber(row.pc_kiem_nhiem1);
	const referenceSalary = toNumber(payload.reference_salary);


	if (luongCb + pcDang1 + pcKiemNhiem1 > 20 * referenceSalary) 
		{
			frappe.model.set_value(row.doctype, row.name, "tong_luong_cb", 20 * referenceSalary);
		} 
	else {
		frappe.model.set_value(row.doctype, row.name, "tong_luong_cb", luongCb + pcDang1 + pcKiemNhiem1);
	}
	row.tong_luong_cb = toNumber(row.tong_luong_cb);

	const EXCLUDED_CONTRACTS = [
		"Hợp đồng thử việc",
		"Hợp đồng tập nghề",
		"Hợp đồng đào tạo nghề",
		"Hợp đồng học nghề",
	];

	// ép số an toàn
	const num = x => +x || 0;

	// 1) Nếu KHÔNG đóng BHXH & ĐPCĐ => luôn 0
	if (row.bhxh !== "1. Đóng BHXH, đóng ĐPCĐ") {
		frappe.model.set_value(row.doctype, row.name, "tru_bhxh", 0);
	} 
	else {
		// 2) Chỉ xét đóng khi CẢ hai loại HĐ (hiện tại & cũ) không thuộc danh sách loại trừ
		const typeNowExcluded = EXCLUDED_CONTRACTS.includes(row.employement_type);
		const typeOldExcluded = EXCLUDED_CONTRACTS.includes(row.employement_type_cur);

		const totalDays = num(row.ngay_cong) + num(row.ngay_cong_cu) + num(row.sophep) + num(row.so_ngay_nghi_vr);
		const allowOverride = String(row.cho_phep_dong_bhxh) === "1" || row.cho_phep_dong_bhxh === 1 || row.cho_phep_dong_bhxh === true;

		let amount = 0;

		if (!typeNowExcluded && !typeOldExcluded && (totalDays >= 14 || allowOverride)) {
			amount = (num(row.tong_luong_cb) * 0.08); // 8% lương cơ bản
		} 
		else {
			amount = 0;
		}

		frappe.model.set_value(row.doctype, row.name, "tru_bhxh", amount);
	}


	if (!row.bhyt) {
		frappe.model.set_value(row.doctype, row.name, "tru_bhyt", row.tong_luong_cb * 0.015);
	} else {
		frappe.model.set_value(row.doctype, row.name, "tru_bhyt", 0);
	}

	if (!row.bhtn) {
		frappe.model.set_value(row.doctype, row.name, "tru_bhtn", row.tong_luong_cb * 0.01);
	} else {
		frappe.model.set_value(row.doctype, row.name, "tru_bhtn", 0);
	}

	frappe.model.set_value(
		row.doctype,
		row.name,
		"xh_yt_tn",
		toNumber(row.tru_bhxh) + toNumber(row.tru_bhyt) + toNumber(row.tru_bhtn)
	);
	if (
	["1. Đóng BHXH, đóng ĐPCĐ", "3. Không đóng BHXH, đóng ĐPCĐ"].includes(row.bhxh)
) {
	const luong = flt(row.tong_luong_cb || 0);
	const dpcd = luong * 0.005;

	frappe.model.set_value(row.doctype, row.name, "doan_phi_cd", dpcd);
}
	frappe.model.set_value(row.doctype, row.name, "sophep", payload.so_phep);
	frappe.model.set_value(row.doctype, row.name, "so_ngay_nghi_vr", payload.so_ngay_nghi_vr);

	const standardWorkingDays = toNumber(frm.doc.standard_working_days);
	if (!standardWorkingDays) {
		frappe.model.set_value(row.doctype, row.name, "tong_thu_nhap", 0);
		frappe.model.set_value(row.doctype, row.name, "thuc_linh", 0);
		if (refresh) {
			frm.refresh_field("items");
		}
		return;
	}

	const soPhep = toNumber(payload.so_phep);
	const soNgayNghiVR = toNumber(payload.so_ngay_nghi_vr);
	const luongNghiPhepVR = (luongCb / standardWorkingDays) * (soPhep + soNgayNghiVR);
	frappe.model.set_value(row.doctype, row.name, "luong_nghiphep_vr", luongNghiPhepVR);

	frappe.model.set_value(row.doctype, row.name, "nghi_kluong_bhxh", payload.nghi_kluong_bhxh);

	const tienLuongHQCV = ((row.muc_luong_theo_hqcv) / standardWorkingDays) * currentWorkingDays;
	frappe.model.set_value(row.doctype, row.name, "tien_luong_hqcv", tienLuongHQCV);
	row.tien_luong_hqcv = tienLuongHQCV;

	const tienLuongHQCVCu =
		previousWorkingDays > 0 && hasPreviousSalaryAmount
			? (toNumber(row.muc_luong_theo_hqcv_cu) / standardWorkingDays) * previousWorkingDays
			: 0;
	frappe.model.set_value(row.doctype, row.name, "tien_luong_hqcv_cu", tienLuongHQCVCu);
	row.tien_luong_hqcv_cu = tienLuongHQCVCu;

	const tienAn =
		(toNumber(payload.meal_allowance) / standardWorkingDays) *
		Math.round(currentWorkingDays + previousWorkingDays);
	frappe.model.set_value(row.doctype, row.name, "tien_an", tienAn);
	row.tien_an = tienAn;

	frappe.model.set_value(
		row.doctype,
		row.name,
		"pc_dang2",
		toNumber(row.hs_pc_dang_1) * corporateMinWage
	);
	frappe.model.set_value(
		row.doctype,
		row.name,
		"pc_kiem_nhiem2",
		toNumber(row.hs_pc_kiem_nhiem1) * corporateMinWage
	);

	if (row.bhxh !== "3. Không đóng BHXH & ĐPCĐ") {
		frappe.model.set_value(row.doctype, row.name, "tien_khoan_ct", toNumber(payload.travel_allowance));
	} else {
		frappe.model.set_value(row.doctype, row.name, "tien_khoan_ct", 0);
	}

	const tienGuiXe = toNumber(payload.tien_gui_xe);
	frappe.model.set_value(row.doctype, row.name, "tien_gui_xe", tienGuiXe);
	row.tien_gui_xe = tienGuiXe;

	const tongThuNhap =
		toNumber(row.pc_dang2) +
		toNumber(row.pc_kiem_nhiem2) +
		toNumber(row.luong_nghiphep_vr) +
		toNumber(row.tien_luong_hqcv) +
		toNumber(row.tien_an) +
		toNumber(row.tien_khoan_ct) +
		toNumber(row.truylinh) +
		toNumber(row.tien_luong_hqcv_cu) +
		toNumber(row.tien_gui_xe);
	frappe.model.set_value(row.doctype, row.name, "tong_thu_nhap", tongThuNhap);

	const tongThuNhapChiuThue = tongThuNhap - toNumber(row.tien_an) - toNumber(row.tien_khoan_ct) - toNumber(row.tien_gui_xe);
	frappe.model.set_value(row.doctype, row.name, "tong_tn_chiu_thue", tongThuNhapChiuThue);

	if (row.dang_vien === "Chính thức") {
		frappe.model.set_value(row.doctype, row.name, "dang_phi", tongThuNhapChiuThue * 0.01);
	} else {
		frappe.model.set_value(row.doctype, row.name, "dang_phi", 0);
	}

	const isFormalContract =
		row.employement_type === "Hợp đồng thử việc" ||
		row.employement_type === "Hợp đồng học nghề" ||
		row.employement_type === "Hợp đồng đào tạo nghề" ||
		row.employement_type === "Hợp đồng tập nghề";

	if (tongThuNhapChiuThue > 2000000 && isFormalContract) 
	{
		frappe.model.set_value(row.doctype, row.name, "thu_nhap_tinh_thue", tongThuNhapChiuThue);
	} 
	else if (tongThuNhapChiuThue <= 2000000 && isFormalContract)
 	{
		frappe.model.set_value(row.doctype, row.name, "thu_nhap_tinh_thue", 0);
	} else if (
		row.employement_type === "HĐLĐ xác định thời hạn" ||
		row.employement_type === "HĐLĐ không xác định thời hạn" ||
		row.employement_type === "Không giao kết HĐLĐ"
	) {
		const taxableBase =
			tongThuNhapChiuThue -
			toNumber(row.tru_bhxh) -
			toNumber(row.tru_bhyt) -
			toNumber(row.tru_bhtn) -
			(toNumber(payload.giam_tru_npt) * toNumber(row.so_npt)) -
			toNumber(payload.giam_tru_gia_canh);
		frappe.model.set_value(
			row.doctype,
			row.name,
			"thu_nhap_tinh_thue",
			Math.max(0, taxableBase)
		);
	}

	const applyFlatTax10 = payload.thue_tam_trich === true || payload.thue_tam_trich === 1 || String(payload.thue_tam_trich) === "1";
	let tncn;

	if (applyFlatTax10) {
		const baseForFlatTax = toNumber(row.tong_tn_chiu_thue) || toNumber(tongThuNhap);
		tncn = Math.round(baseForFlatTax * 0.1);
	} else {
		const taxableIncome = Math.max(0, +row.thu_nhap_tinh_thue || 0);
		const extraWithheldTax = toNumber(payload.thue_tncn_trich_them);
		const bracketsRaw = Array.isArray(payload.tax_brackets) ? payload.tax_brackets : [];
		const brackets = bracketsRaw
			.map((b) => ({
				rate: +((b.rate ?? b.percent) || 0),
				from: +((b.from ?? b.from_cur) || 0),
				to: +((b.to ?? b.to_cur) || 0) || Infinity,
			}))
			.filter((b) => b.rate > 0 && b.to > b.from)
			.sort((a, b) => a.from - b.from);

		let totalTax = 0;
		for (const b of brackets) {
			if (taxableIncome <= b.from) break;
			const upper = Math.min(taxableIncome, b.to);
			const chunk = Math.max(0, upper - b.from);
			if (chunk <= 0) continue;
			totalTax += chunk * (b.rate / 100);
		}

		tncn = Math.round(totalTax) + extraWithheldTax;
	}
	frappe.model.set_value(row.doctype, row.name, "tncn_tam_thu", tncn);
	row.tncn_tam_thu = tncn;

	const thucLinh =
		tongThuNhap -
		toNumber(row.xh_yt_tn) -
		toNumber(row.doan_phi_cd) -
		toNumber(row.dang_phi) -
		toNumber(row.tncn_tam_thu) -
		toNumber(row.khac) -
		toNumber(row.truy_thu) +
		toNumber(row.duoc_hoan_lai);
	frappe.model.set_value(row.doctype, row.name, "thuc_linh", thucLinh);

	if (refresh) {
		frm.refresh_field("items");
	}
}


function compute_all_items(frm, rows = []) {
	const targets = rows.length ? rows : frm.doc.items || [];
	const computables = targets.filter((row) => row && row.employee);
	if (!computables.length) {
		return Promise.resolve();
	}

	return computables.reduce((promise, row) => {
		return promise.then(() =>
			Promise.resolve(frm.events.compute_row(frm, row, { freeze: false, refresh: false }))
		);
	}, Promise.resolve());
}

function toNumber(value) {
	const num = Number(value);
	return Number.isFinite(num) ? num : 0;
}

// ==== Quyền tính lương ====
const HR_SALARY_USERS = new Set([
	"tult@vinatex.com.vn",
	"hoaltm@vinatex.com.vn",
	"thaottt@vinatex.com.vn",
]);

function canManagePayroll() {
	const user = frappe.session?.user;
	if (!user) return false;
	if (user === "Administrator") return true;
	return HR_SALARY_USERS.has(user);
}
