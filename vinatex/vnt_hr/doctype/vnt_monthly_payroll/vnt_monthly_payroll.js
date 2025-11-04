// Copyright (c) 2025, vinatex and contributors
// For license information, please see license.txt

frappe.ui.form.on("VNT Monthly Payroll", {
	
    refresh(frm) {
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
    },
    month (frm) {
        if (frm.doc.month && frm.doc.year) {
            const month = parseInt(frm.doc.month, 10);
            const year = parseInt(frm.doc.year, 10);
            get_standard_working_days(frm, month, year);
        }
    },
    year (frm) {
        if (frm.doc.month && frm.doc.year) {
            const month = parseInt(frm.doc.month, 10);
            const year = parseInt(frm.doc.year, 10);
            get_standard_working_days(frm, month, year);
        }
    },
	get_salary(frm) {
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
				freeze_message: freeze
					? __("Đang tính lương cho {0}", [row.employee_name || row.employee])
					: undefined,
			})
			.then((r) => {
				if (!r || !r.message) return;

				// ====== Các tính toán đầu vào trước thuế (giữ nguyên logic của bạn) ======
				frappe.model.set_value(
					row.doctype,
					row.name,
					"luong_cb",
					r.message.regional_minimum_wage * row.hs_luong_cb
				);
				frappe.model.set_value(
					row.doctype,
					row.name,
					"pc_dang1",
					r.message.regional_minimum_wage * row.hs_pc_dang_1
				);
				frappe.model.set_value(
					row.doctype,
					row.name,
					"pc_kiem_nhiem1",
					r.message.regional_minimum_wage * row.hs_pc_kiem_nhiem1
				);

				if (row.bhxh == "")
					frappe.model.set_value(row.doctype, row.name, "tong_luong_cb", 0);
				else if (
					toNumber(row.luong_cb) + toNumber(row.pc_dang1) + toNumber(row.pc_kiem_nhiem1) >
					20 * r.message.reference_salary
				)
					frappe.model.set_value(
						row.doctype,
						row.name,
						"tong_luong_cb",
						20 * r.message.reference_salary
					);
				else
					frappe.model.set_value(
						row.doctype,
						row.name,
						"tong_luong_cb",
						toNumber(row.luong_cb) +
							toNumber(row.pc_dang1) +
							toNumber(row.pc_kiem_nhiem1)
					);

				if (!row.bhxh)
					frappe.model.set_value(
						row.doctype,
						row.name,
						"tru_bhxh",
						row.tong_luong_cb * 0.08
					);
				else frappe.model.set_value(row.doctype, row.name, "tru_bhxh", 0);

				if (!row.bhyt)
					frappe.model.set_value(
						row.doctype,
						row.name,
						"tru_bhyt",
						row.tong_luong_cb * 0.015
					);
				else frappe.model.set_value(row.doctype, row.name, "tru_bhyt", 0);

				if (!row.bhtn)
					frappe.model.set_value(
						row.doctype,
						row.name,
						"tru_bhtn",
						row.tong_luong_cb * 0.01
					);
				else frappe.model.set_value(row.doctype, row.name, "tru_bhtn", 0);

				frappe.model.set_value(
					row.doctype,
					row.name,
					"xh_yt_tn",
					toNumber(row.tru_bhxh) +
						toNumber(row.tru_bhyt) +
						toNumber(row.tru_bhtn)
				);

				frappe.model.set_value(
					row.doctype,
					row.name,
					"doan_phi_cd",
					row.tong_luong_cb * 0.005
				);

				frappe.model.set_value(row.doctype, row.name, "sophep", r.message.so_phep);
				frappe.model.set_value(
					row.doctype,
					row.name,
					"so_ngay_nghi_vr",
					r.message.so_ngay_nghi_vr
				);

				const standard_working_days = toNumber(frm.doc.standard_working_days);
				if (!standard_working_days) {
					frappe.model.set_value(row.doctype, row.name, "tong_thu_nhap", 0);
					frappe.model.set_value(row.doctype, row.name, "thuc_linh", 0);
					if (refresh) {
						frm.refresh_field("items");
					}
					return;
				}

				const so_phep = toNumber(r.message.so_phep);
				const so_ngay_nghi_vr = toNumber(r.message.so_ngay_nghi_vr);
				let luong_nghiphep_vr =
					(toNumber(row.luong_cb) / standard_working_days) *
					(so_phep + so_ngay_nghi_vr);
				frappe.model.set_value(
					row.doctype,
					row.name,
					"luong_nghiphep_vr",
					luong_nghiphep_vr
				);

				frappe.model.set_value(
					row.doctype,
					row.name,
					"nghi_kluong_bhxh",
					r.message.nghi_kluong_bhxh
				);

				frappe.model.set_value(
					row.doctype,
					row.name,
					"ngay_cong",
					standard_working_days -
						so_phep -
						so_ngay_nghi_vr -
						toNumber(row.nghi_kluong_bhxh)
				);

				frappe.model.set_value(
					row.doctype,
					row.name,
					"tien_luong_hqcv",
					((toNumber(row.he_so_cbnv) * toNumber(r.message.corporate_minimum_wage)) /
						standard_working_days) *
						toNumber(row.ngay_cong)
				);

				frappe.model.set_value(
					row.doctype,
					row.name,
					"pc_dang2",
					row.hs_pc_dang_1 * r.message.corporate_minimum_wage
				);
				frappe.model.set_value(
					row.doctype,
					row.name,
					"pc_kiem_nhiem2",
					row.hs_pc_kiem_nhiem1 * r.message.corporate_minimum_wage
				);

				frappe.model.set_value(
					row.doctype,
					row.name,
					"tien_an",
					(toNumber(r.message.meal_allowance) / standard_working_days) *
						toNumber(row.ngay_cong)
				);
				frappe.model.set_value(
					row.doctype,
					row.name,
					"tien_khoan_ct",
					r.message.travel_allowance
				);

				frappe.model.set_value(
					row.doctype,
					row.name,
					"tong_thu_nhap",
					toNumber(row.pc_dang2) +
						toNumber(row.pc_kiem_nhiem2) +
						toNumber(row.luong_nghiphep_vr) +
						toNumber(row.tien_luong_hqcv) +
						toNumber(row.tien_an) +
						toNumber(row.tien_khoan_ct) +
						toNumber(row.truylinh)
				);

				frappe.model.set_value(
					row.doctype,
					row.name,
					"tong_tn_chiu_thue",
					row.tong_thu_nhap - row.tien_an - row.tien_khoan_ct
				);

				if (row.dang_vien == "Chính thức")
					frappe.model.set_value(
						row.doctype,
						row.name,
						"dang_phi",
						row.tong_tn_chiu_thue * 0.001
					);
				else frappe.model.set_value(row.doctype, row.name, "dang_phi", 0);

				// (36) Thu nhập tính thuế (giữ điều kiện HĐLĐ của bạn)
				if (
					row.tong_tn_chiu_thue > 2000000 &&
					row.employement_type !== "HĐLĐ xác định thời hạn" &&
					row.employement_type !== "HĐLĐ không xác định thời hạn"
				) {
					frappe.model.set_value(
						row.doctype,
						row.name,
						"thu_nhap_tinh_thue",
						row.tong_tn_chiu_thue
					);
				} else if (
					row.tong_tn_chiu_thue <= 2000000 &&
					row.employement_type !== "HĐLĐ xác định thời hạn" &&
					row.employement_type !== "HĐLĐ không xác định thời hạn"
				) {
					frappe.model.set_value(
						row.doctype,
						row.name,
						"thu_nhap_tinh_thue",
						0
					);
				} else if (
					row.employement_type === "HĐLĐ xác định thời hạn" ||
					row.employement_type === "HĐLĐ không xác định thời hạn"
				)
				if (
					(row.tong_tn_chiu_thue - row.tru_bhxh - row.tru_bhyt - row.tru_bhtn - (r.message.giam_tru_npt * row.so_npt) - r.message.giam_tru_gia_canh) >= 0 )
					{
					frappe.model.set_value(
						row.doctype,
						row.name,
						"thu_nhap_tinh_thue",
						row.tong_tn_chiu_thue -
							row.tru_bhxh -
							row.tru_bhyt -
							row.tru_bhtn -
							(+r.message.giam_tru_npt) * (+row.so_npt) -
							(+r.message.giam_tru_gia_canh)
					);
				}
				else
				{
				}

				// ===== (37) Thuế TNCN: dùng THẲNG (36) và tính lũy tiến =====
				const taxable = Math.max(0, +row.thu_nhap_tinh_thue || 0);

				// chuẩn hoá bậc thuế từ server
				const brackets_raw = Array.isArray(r.message.tax_brackets)
					? r.message.tax_brackets
					: [];
				const brackets = brackets_raw
					.map((b) => ({
						rate: +((b.rate ?? b.percent) || 0), // %
						from: +((b.from ?? b.from_cur) || 0),
						to:
							+((b.to ?? b.to_cur) || 0) || Infinity, // 0 => vô hạn
					}))
					.filter((b) => b.rate > 0 && b.to > b.from)
					.sort((a, b) => a.from - b.from);

				let total_tax = 0;
				const breakdown = [];
				for (const b of brackets) {
					if (taxable <= b.from) break;
					const upper = Math.min(taxable, b.to);
					const chunk = Math.max(0, upper - b.from); // [from, to)
					if (chunk <= 0) continue;
					const tax_here = chunk * (b.rate / 100);
					total_tax += tax_here;
					breakdown.push({
						from: b.from,
						to: Number.isFinite(b.to) ? b.to : null, // null = vô hạn
						rate: b.rate,
						amount: chunk,
						tax: tax_here,
					});
				}

				const tncn = Math.round(total_tax);
				frappe.model.set_value(row.doctype, row.name, "tncn_tam_thu", tncn);

				// nếu bạn có field để lưu breakdown (JSON hoặc child table) thì gán ở đây
				// frappe.model.set_value(row.doctype, row.name, "tncn_breakdown_json", JSON.stringify(breakdown));

                //thu nhập thực lĩnh (41)
                frappe.model.set_value(row.doctype, row.name, "thuc_linh", (row.tong_thu_nhap - row.xh_yt_tn - row.doan_phi_cd - row.dang_phi -row.tncn_tam_thu - row.khac - row.truy_thu + row.duoc_hoan_lai))
				if (refresh) {
					frm.refresh_field("items");
				}
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
});


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
