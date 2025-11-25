# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

import math
from calendar import monthrange
from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, now_datetime

from vinatex.vnt_hr.doctype.vnt_monthly_payroll.vnt_monthly_payroll import compute_item as compute_monthly_payroll_item
from vinatex.vnt_hr.doctype.vnt_salary_slip.vnt_salary_slip import VNTSalarySlip


def execute(filters=None):
	filters = _prepare_filters(filters or {})
	columns = _get_columns()
	data = _get_data(filters)
	return columns, data


def _get_columns():
	return [
		{"label": _("Mã nhân sự"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
		{"label": _("Tên nhân sự"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": _("Công ty"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
		{"label": _("Phòng ban"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 150},
		{"label": _("Năm"), "fieldname": "year", "fieldtype": "Int", "width": 80},
		{"label": _("Lương tháng đã chọn"), "fieldname": "current_month_net_income", "fieldtype": "Currency", "width": 160},
		{"label": _("Lương tháng trước"), "fieldname": "previous_month_net_income", "fieldtype": "Currency", "width": 150},
		{"label": _("Số tháng có bảng lương"), "fieldname": "salary_month_count", "fieldtype": "Int", "width": 170},
		{"label": _("Tổng thu nhập"), "fieldname": "total_gross_income", "fieldtype": "Float", "width": 150},
		{"label": _("Tổng phụ cấp"), "fieldname": "total_allowance", "fieldtype": "Currency", "width": 150},
		{"label": _("Thuế TNCN (tạm thu)"), "fieldname": "total_income_tax", "fieldtype": "Currency", "width": 150},
		{"label": _("Thuế TNCN phụ cấp"), "fieldname": "total_allowance_tax", "fieldtype": "Currency", "width": 160},
		{"label": _("Thực lĩnh"), "fieldname": "total_net_income", "fieldtype": "Currency", "width": 150},
		{"label": _("Thực lĩnh phụ cấp"), "fieldname": "total_allowance_net", "fieldtype": "Currency", "width": 160},
	]


def _prepare_filters(incoming_filters: dict) -> dict:
	prepared = dict(incoming_filters or {})
	if not prepared.get("year"):
		prepared["year"] = now_datetime().year

	prepared["year"] = cint(prepared["year"])
	if not prepared["year"]:
		frappe.throw(_("Vui lòng chọn Năm hợp lệ."))

	if not prepared.get("month"):
		prepared["month"] = now_datetime().month

	prepared["month"] = cint(prepared["month"])
	if not 1 <= prepared["month"] <= 12:
		frappe.throw(_("Vui lòng chọn Tháng hợp lệ."))
	prepared["previous_month"] = prepared["month"] - 1 if prepared["month"] > 1 else None

	employee_code = _get_employee_of_user()
	if not employee_code:
		frappe.throw(_("Tài khoản của bạn chưa được liên kết với hồ sơ nhân sự nào. Vui lòng liên hệ Ban QLNNL."))
	prepared["employee"] = employee_code

	return prepared


def _get_employee_of_user() -> str | None:
	return frappe.db.get_value(
		"Employee",
		{"user_id": frappe.session.user, "status": "Active"},
		"name",
	)


def _get_monthly_payroll_net_income(employee: str, month: int | str, year: int | str, company: str | None = None) -> float | None:
	"""
	Tính lương tháng theo công thức VNT Monthly Payroll (compute_item + công thức JS applyPayrollPayload).
	Dùng trực tiếp dữ liệu chấm công/contract/salary history → không phụ thuộc salary slip.
	"""
	if not (employee and month and year):
		return None

	try:
		payload = compute_monthly_payroll_item(
			employee=employee,
			company=company,
			month=cint(month),
			year=cint(year),
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Annual salary: compute_item failed")
		return None

	if not payload:
		return None

	employee_ctx = _get_employee_payroll_fields(employee)
	if not employee_ctx:
		return None

	try:
		return _calculate_net_from_payload(employee_ctx, payload, cint(year), cint(month))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Annual salary: net computation failed")
		return None


def _get_employee_payroll_fields(employee: str) -> dict:
	if not employee:
		return {}

	row = frappe.db.get_value(
		"Employee",
		employee,
		[
			"custom_basic_salary_coefficient",
			"custom_allowance_coefficient_1",
			"custom_allowance_coefficient_2",
			"custom_no_social_insurance",
			"custom_party_member",
			"custom_relation_number",
			"employment_type",
		],
		as_dict=True,
	)
	if not row:
		return {}

	return {
		"hs_luong_cb": flt(row.custom_basic_salary_coefficient),
		"hs_pc_dang_1": flt(row.custom_allowance_coefficient_1),
		"hs_pc_kiem_nhiem1": flt(row.custom_allowance_coefficient_2),
		"bhxh": row.custom_no_social_insurance or "",
		"dang_vien": row.custom_party_member or "",
		"so_npt": cint(row.custom_relation_number or 0),
		"employment_type": row.employment_type or "",
	}


def _js_round(value: float) -> int:
	try:
		val = float(value)
	except Exception:
		return 0
	if val >= 0:
		return int(math.floor(val + 0.5))
	return int(math.ceil(val - 0.5))


def _get_standard_working_days_py(year: int, month: int) -> int:
	"""Số ngày công chuẩn (trừ T7-CN) giống hàm JS get_standard_working_days."""
	if not (year and month):
		return 0
	working = 0
	total_days = monthrange(year, month)[1]
	for day in range(1, total_days + 1):
		dow = date(year, month, day).weekday()  # Mon=0 ... Sun=6
		if dow not in (5, 6):
			working += 1
	return working


def _calculate_net_from_payload(employee_ctx: dict, payload: dict, year: int, month: int) -> float:
	standard_days = _get_standard_working_days_py(year, month)
	if not standard_days:
		return 0.0

	# Các hệ số/flag lấy từ hồ sơ nhân sự
	hs_luong_cb = flt(employee_ctx.get("hs_luong_cb"))
	hs_pc_dang_1 = flt(employee_ctx.get("hs_pc_dang_1"))
	hs_pc_kiem_nhiem1 = flt(employee_ctx.get("hs_pc_kiem_nhiem1"))
	bhxh_flag = employee_ctx.get("bhxh") or ""
	dang_vien = (employee_ctx.get("dang_vien") or "").strip()
	so_npt = cint(employee_ctx.get("so_npt") or 0)
	emp_contract_type = (employee_ctx.get("employment_type") or "").strip()

	reference_salary = flt(payload.get("reference_salary"))
	regional_minimum_wage = flt(payload.get("regional_minimum_wage"))
	corporate_minimum_wage = flt(payload.get("corporate_minimum_wage"))
	meal_allowance = flt(payload.get("meal_allowance"))
	travel_allowance = flt(payload.get("travel_allowance"))

	so_phep = flt(payload.get("so_phep"))
	so_ngay_nghi_vr = flt(payload.get("so_ngay_nghi_vr"))
	nghi_kluong_bhxh = flt(payload.get("nghi_kluong_bhxh"))

	current_working_days = flt(payload.get("current_working_days") or payload.get("ngaycong"))
	previous_working_days = flt(payload.get("previous_working_days"))

	current_contract_type = (payload.get("current_contract_type") or emp_contract_type or "").strip()
	previous_contract_type = (payload.get("previous_contract_type") or "").strip()

	latest_salary_coefficient = payload.get("latest_salary_coefficient")
	current_salary_coefficient = payload.get("current_salary_coefficient")
	previous_salary_coefficient = payload.get("previous_salary_coefficient")

	latest_salary_amount = payload.get("latest_salary_amount")
	current_salary_amount = payload.get("current_salary_amount")
	previous_salary_amount = payload.get("previous_salary_amount")

	# Hệ số & mức lương theo hợp đồng
	if current_salary_coefficient is not None:
		he_so_cbnv = flt(current_salary_coefficient)
	elif latest_salary_coefficient is not None:
		he_so_cbnv = flt(latest_salary_coefficient)
	else:
		he_so_cbnv = 0

	if current_salary_amount is not None:
		muc_luong_theo_hqcv = flt(current_salary_amount)
	elif latest_salary_amount is not None:
		muc_luong_theo_hqcv = flt(latest_salary_amount)
	else:
		muc_luong_theo_hqcv = 0

	muc_luong_theo_hqcv_cu = 0.0
	if previous_working_days > 0 and previous_salary_amount is not None:
		muc_luong_theo_hqcv_cu = flt(previous_salary_amount)

	# Lương cơ bản & phụ cấp 1
	luong_cb = regional_minimum_wage * hs_luong_cb
	pc_dang1 = regional_minimum_wage * hs_pc_dang_1
	pc_kiem_nhiem1 = regional_minimum_wage * hs_pc_kiem_nhiem1

	# Tổng lương tính BHXH (giới hạn 20 * reference_salary)
	if bhxh_flag == "3. Không đóng BHXH & ĐPCĐ":
		tong_luong_cb = 0
	else:
		gross_base = luong_cb + pc_dang1 + pc_kiem_nhiem1
		max_base = reference_salary * 20 if reference_salary else gross_base
		tong_luong_cb = min(gross_base, max_base)

	excluded_contracts = {
		"Hợp đồng thử việc",
		"Hợp đồng tập nghề",
		"Hợp đồng đào tạo nghề",
		"Hợp đồng học nghề",
	}

	total_days_for_bhxh = (
		current_working_days + previous_working_days + so_phep + so_ngay_nghi_vr
	)
	type_now_excluded = current_contract_type in excluded_contracts
	type_old_excluded = previous_contract_type in excluded_contracts
	allow_override_bhxh = False

	if bhxh_flag == "3. Không đóng BHXH & ĐPCĐ":
		tru_bhxh = 0
	elif (not type_now_excluded and not type_old_excluded) and (total_days_for_bhxh >= 14 or allow_override_bhxh):
		tru_bhxh = tong_luong_cb * 0.08
	else:
		tru_bhxh = 0

	tru_bhyt = 0 if employee_ctx.get("bhyt") else tong_luong_cb * 0.015
	tru_bhtn = 0 if employee_ctx.get("bhtn") else tong_luong_cb * 0.01
	xh_yt_tn = tru_bhxh + tru_bhyt + tru_bhtn

	doan_phi_cd = tong_luong_cb * 0.005

	# Lương nghỉ phép & ngày VR
	luong_nghiphep_vr = 0
	if standard_days:
		luong_nghiphep_vr = (luong_cb / standard_days) * (so_phep + so_ngay_nghi_vr)

	# Lương HQCV hiện tại & cũ
	tien_luong_hqcv = 0
	tien_luong_hqcv_cu = 0
	if standard_days:
		tien_luong_hqcv = (muc_luong_theo_hqcv / standard_days) * current_working_days
		if previous_working_days > 0 and previous_salary_coefficient is not None:
			tien_luong_hqcv_cu = (muc_luong_theo_hqcv_cu / standard_days) * previous_working_days

	# Tiền ăn ca
	tien_an = 0
	if standard_days:
		tien_an = (meal_allowance / standard_days) * _js_round(current_working_days + previous_working_days)

	# Phụ cấp loại 2
	pc_dang2 = hs_pc_dang_1 * corporate_minimum_wage
	pc_kiem_nhiem2 = hs_pc_kiem_nhiem1 * corporate_minimum_wage

	# Công tác phí
	tien_khoan_ct = 0 if bhxh_flag == "3. Không đóng BHXH & ĐPCĐ" else travel_allowance

	tong_thu_nhap = (
		pc_dang2
		+ pc_kiem_nhiem2
		+ luong_nghiphep_vr
		+ tien_luong_hqcv
		+ tien_an
		+ tien_khoan_ct
		+ flt(payload.get("truylinh"))
		+ tien_luong_hqcv_cu
	)

	tong_tn_chiu_thue = tong_thu_nhap - tien_an - tien_khoan_ct

	dang_phi = tong_tn_chiu_thue * 0.01 if dang_vien == "Chính thức" else 0

	# Thu nhập tính thuế
	formal_contracts = {
		"Hợp đồng thử việc",
		"Hợp đồng học nghề",
		"Hợp đồng đào tạo nghề",
		"Hợp đồng tập nghề",
	}
	long_term_contracts = {
		"HĐLĐ xác định thời hạn",
		"HĐLĐ không xác định thời hạn",
		"Không giao kết HĐLĐ",
	}

	taxable_income = 0
	if current_contract_type in formal_contracts:
		if tong_tn_chiu_thue > 2_000_000:
			taxable_income = tong_tn_chiu_thue
		else:
			taxable_income = 0
	elif current_contract_type in long_term_contracts:
		_base = (
			tong_tn_chiu_thue
			- tru_bhxh
			- tru_bhyt
			- tru_bhtn
			- (flt(payload.get("giam_tru_npt")) * so_npt)
			- flt(payload.get("giam_tru_gia_canh"))
		)
		taxable_income = max(0, _base)

	# Thuế TNCN lũy tiến
	brackets = []
	for b in payload.get("tax_brackets") or []:
		rate = flt(b.get("rate") or b.get("percent"))
		from_ = flt(b.get("from") or b.get("from_cur"))
		to_ = b.get("to") if b.get("to") not in (None, "") else b.get("to_cur")
		to_val = float("inf") if to_ in (None, "", 0) else flt(to_)
		if rate > 0 and to_val > from_:
			brackets.append({"rate": rate, "from": from_, "to": to_val})
	brackets = sorted(brackets, key=lambda b: b["from"])

	total_tax = 0.0
	for b in brackets:
		if taxable_income <= b["from"]:
			break
		upper = min(taxable_income, b["to"])
		chunk = max(0, upper - b["from"])
		if chunk > 0:
			total_tax += chunk * (b["rate"] / 100.0)
	tncn_tam_thu = _js_round(total_tax)

	thuc_linh = (
		tong_thu_nhap
	)
	return flt(thuc_linh)


@frappe.whitelist()
def _get_data(filters: dict):
	conditions = ["slip.docstatus = 1", "slip.year = %(year)s"]
	params = {"year": filters["year"], "month": f"{filters['month']:02d}"}
	prev_month = filters.get("previous_month")
	if filters.get("employee"):
		conditions.append("slip.employee = %(employee)s")
		params["employee"] = filters["employee"]

	where_clause = " AND ".join(conditions)
	item_subquery = """
		SELECT
			parent,
			SUM(COALESCE(tong, 0)) AS total_allowance,
			SUM(COALESCE(thue_tncn, 0)) AS total_allowance_tax,
			SUM(COALESCE(thuc_linh, 0)) AS total_allowance_net
		FROM `tabVNT Salary Slip Item`
		GROUP BY parent
	"""

	sql = f"""
		SELECT
			slip.name,
			slip.employee,
			COALESCE(emp.employee_name, slip.employee) AS employee_name,
			emp.company,
			emp.department,
			slip.year,
			slip.month,
			slip.tong_thu_nhap,
			slip.thuc_linh,
			slip.tong_thu_nhap_encrypted,
			slip.thuc_linh_encrypted,
			COALESCE(slip.thue_tncn, 0) + COALESCE(slip.thue_tncn_nam_truoc, 0) AS income_tax,
			COALESCE(item.total_allowance, 0) AS total_allowance,
			COALESCE(item.total_allowance_tax, 0) AS total_allowance_tax,
			COALESCE(item.total_allowance_net, 0) AS total_allowance_net
		FROM `tabVNT Salary Slip` AS slip
		LEFT JOIN `tabEmployee` AS emp ON emp.name = slip.employee
		LEFT JOIN ({item_subquery}) AS item ON item.parent = slip.name
		WHERE {where_clause}
		ORDER BY slip.employee, slip.year, slip.month
	"""

	rows = frappe.db.sql(sql, params, as_dict=True)
	grouped: dict[tuple[str, int], dict] = {}
	for row in rows:
		key = (row["employee"], cint(row["year"]))
		target = grouped.setdefault(
			key,
			{
				"employee": row["employee"],
				"employee_name": row.get("employee_name") or row["employee"],
				"company": row.get("company") or "",
				"department": row.get("department") or "",
				"year": cint(row["year"]),
				"salary_month_count": set(),
				"total_gross_income": 0.0,
				"total_allowance": 0.0,
				"total_income_tax": 0.0,
				"total_allowance_tax": 0.0,
				"total_net_income": 0.0,
				"total_allowance_net": 0.0,
				"current_month_net_income": 0.0,
				"previous_month_net_income": 0.0,
			},
		)

		gross, net = _get_salary_values_with_fallback(row)
		month = cstr(row.get("month")).zfill(2)
		target["salary_month_count"].add(month)
		target["total_gross_income"] += gross
		target["total_allowance"] += flt(row.get("total_allowance"))
		target["total_income_tax"] += flt(row.get("income_tax"))
		target["total_allowance_tax"] += flt(row.get("total_allowance_tax"))
		target["total_net_income"] += net
		target["total_allowance_net"] += flt(row.get("total_allowance_net"))

		if month == params["month"]:
			target["current_month_net_income"] += net
		if prev_month and month == params.get("prev_month"):
			target["previous_month_net_income"] += net

	results = []
	for group in grouped.values():
		group["salary_month_count"] = len(group["salary_month_count"])
		results.append(group)

	results.sort(key=lambda r: (r["employee"], r["year"]))

	for row in results:
		current_month_net = _get_monthly_payroll_net_income(
			row.get("employee"),
			filters.get("month"),
			filters.get("year"),
			row.get("company"),
		)
		row["current_month_net_income"] = current_month_net if current_month_net is not None else row["current_month_net_income"]
	return results


def _get_salary_values_with_fallback(row: dict) -> tuple[float, float]:
	"""
	Sử dụng giá trị thường nếu có; nếu thiếu thì giải mã từ ciphertext.
	Trả về (gross, net) dạng float.
	"""
	gross = row.get("tong_thu_nhap")
	net = row.get("thuc_linh")
	if gross in (None, "") or net in (None, ""):
		decrypted = VNTSalarySlip.decrypt_salary_values(
			tong_thu_nhap_encrypted=row.get("tong_thu_nhap_encrypted"),
			thuc_linh_encrypted=row.get("thuc_linh_encrypted"),
		)
		if gross in (None, ""):
			gross = decrypted.get("tong_thu_nhap")
		if net in (None, ""):
			net = decrypted.get("thuc_linh")
	frappe.log_error(f"Decrypted values: gross={gross}, net={net}", "Annual salary: decryption log")
	return flt(gross), flt(net)

# Nếu file này chưa có 2 hàm dưới thì giữ lại, nếu có rồi thì khỏi thêm
def _get_employee_of_user() -> str | None:
	return frappe.db.get_value(
		"Employee",
		{"user_id": frappe.session.user, "status": "Active"},
		"name",
	)


def _get_year_month_defaults(year: int | None = None, month: int | None = None) -> dict:
	"""Trả về year, month, previous_month dùng chung cho KPI."""
	dt = now_datetime()
	year = cint(year or dt.year)
	month = cint(month or dt.month)

	if not 1 <= month <= 12:
		frappe.throw(_("Vui lòng chọn Tháng hợp lệ."))

	previous_month = month - 1 if month > 1 else None

	return {
		"year": year,
		"month": month,
		"previous_month": previous_month,
	}


@frappe.whitelist()
def get_salary_kpi(year: int | None = None, month: int | None = None):
	"""
	Trả về 4 KPI + thông tin context:
	- year_to_date_net: Thực lĩnh từ đầu năm
	- previous_month_salary: Lương tháng trước
	- previous_month_allowance: Phụ cấp tháng trước
	- current_month_salary: Lương tháng hiện tại
	- kèm: employee, employee_name, year, month, previous_month
	"""

	# 1. Xác định employee theo user đăng nhập
	employee = _get_employee_of_user()
	if not employee:
		return
		# frappe.throw(_("Tài khoản của bạn chưa được liên kết với hồ sơ nhân sự nào."))

	# 2. Xác định năm / tháng / tháng trước
	ym = _get_year_month_defaults(year, month)

	params = {
		"employee": employee,
		"year": ym["year"],
		"month": f"{ym['month']:02d}",
	}

	# Lấy thêm thông tin nhân sự
	emp_doc = frappe.db.get_value(
		"Employee",
		employee,
		["employee_name", "company", "department"],
		as_dict=True,
	) or {}

	# Subquery tính phụ cấp thực lĩnh theo từng bảng lương
	item_subquery = """
		SELECT
			parent,
			SUM(COALESCE(tong, 0)) AS total_allowance_net
		FROM `tabVNT Salary Slip Item`
		GROUP BY parent
	"""

	select_fields = [
		#tong thu nhap tu dau nam
		"SUM(COALESCE(slip.tong_thu_nhap, 0)) AS year_to_date_net",
		# Lương tháng hiện tại
		"SUM(CASE WHEN slip.month = %(month)s THEN COALESCE(slip.tong_thu_nhap, 0) ELSE 0 END) AS current_month_salary",
	]

	prev_month = ym["previous_month"]
	if prev_month:
		params["prev_month"] = f"{prev_month:02d}"
		select_fields.append(
			"SUM(CASE WHEN slip.month = %(prev_month)s THEN COALESCE(slip.tong_thu_nhap, 0) ELSE 0 END) AS previous_month_salary"
		)
		select_fields.append(
			"SUM(CASE WHEN slip.month = %(prev_month)s THEN COALESCE(item.total_allowance_net, 0) ELSE 0 END) AS previous_month_allowance"
		)
	else:
		# Tháng 1: không có tháng trước → 0
		select_fields.append("0 AS previous_month_salary")
		select_fields.append("0 AS previous_month_allowance")

	sql = f"""
		SELECT
			{", ".join(select_fields)}
		FROM `tabVNT Salary Slip` AS slip
		LEFT JOIN ({item_subquery}) AS item ON item.parent = slip.name
		WHERE slip.docstatus = 1
		  AND slip.year = %(year)s
		  AND slip.employee = %(employee)s
	"""

	result = frappe.db.sql(sql, params, as_dict=True)
	row = result[0] if result else {}
		# lương tháng hiện tại
	now_dt = now_datetime()
	emp_company = frappe.db.get_value("Employee", employee, "company")
	salary_current_month = _get_monthly_payroll_net_income(
		employee,
		now_dt.month,
		now_dt.year,
		emp_company,
	) or 0
	return {
		# 4 KPI
		"year_to_date_net": _js_round(row.get("year_to_date_net") or 0),
		"previous_month_salary": _js_round(row.get("previous_month_salary") or 0),
		"previous_month_allowance": _js_round(row.get("previous_month_allowance") or 0),
		"salary_current_month": _js_round(salary_current_month or 0),
		# Thông tin context cho front-end
		"employee": employee,
		"employee_name": emp_doc.get("employee_name") or "",
		"company": emp_doc.get("company") or "",
		"department": emp_doc.get("department") or "",
		"year": ym["year"],
		"month": ym["month"],
		"previous_month": ym["previous_month"],
	}

@frappe.whitelist()
def get_salary_table(year: int | None = None):
	"""
	Trả về list các dòng chi tiết (không gộp):
	- month
	- year
	- ... các cột của slip
	- ... các cột của item (nếu có)
	cho nhân sự đang login.
	"""

	employee = _get_employee_of_user()
	if not employee:
		return

	conditions = ["slip.docstatus = 1", "slip.employee = %(employee)s"]
	params = {"employee": employee}

	if year:
		params["year"] = cint(year)
		conditions.append("slip.year = %(year)s")

	where_clause = " AND ".join(conditions)

	# Không group by nữa, join trực tiếp để ra từng dòng item
	# Nếu 1 slip có n item -> ra n dòng
	# Nếu 1 slip không có item -> ra 1 dòng (do LEFT JOIN), các cột item là NULL -> xử lý COALESCE về 0 hoặc để trống
	sql = f"""
		SELECT
			slip.year,
			slip.month,
			-- Thông tin từ Slip
			slip.tong_thu_nhap AS slip_salary,
			(
				COALESCE(slip.pc_dang2, 0)
			  + COALESCE(slip.pc_kiem_nhiem2, 0)
			  + COALESCE(slip.cong_tac_phi, 0)
			  + COALESCE(slip.tien_an_ca, 0)
			) AS slip_allowance,
			(
				COALESCE(slip.thue_tncn, 0)
			  + COALESCE(slip.thue_tncn_nam_truoc, 0)
			) AS slip_tax,
			slip.thuc_linh AS slip_net,

			-- Thông tin từ Item (bảng con)
			item.allowance_type,
			item.amount AS item_amount,
			item.thue_tncn AS item_tax,
			item.thuc_linh AS item_net

		FROM `tabVNT Salary Slip` AS slip
		LEFT JOIN `tabVNT Salary Slip Item` AS item ON item.parent = slip.name
		WHERE {where_clause}
		ORDER BY slip.year, slip.month, item.idx
	"""

	rows = frappe.db.sql(sql, params, as_dict=True)

	# Chuyển month dạng "01" / "1" về int cho dễ đọc
	for row in rows:
		# try:
		# 	row["month"] = cint(row.get("month"))
		# except Exception:
		# 	pass
		
		# Xử lý các field item nếu null (do left join mà ko có item)
		if row.get("item_amount") is None: row["item_amount"] = 0
		if row.get("item_tax") is None: row["item_tax"] = 0
		if row.get("item_net") is None: row["item_net"] = 0
		if row.get("allowance_type") is None: row["allowance_type"] = ""
		# Làm tròn VNĐ (không lấy phần thập phân)
		row["slip_salary"] = _js_round(row.get("slip_salary") or 0)
		row["slip_allowance"] = _js_round(row.get("slip_allowance") or 0)
		row["slip_tax"] = _js_round(row.get("slip_tax") or 0)
		row["slip_net"] = _js_round(row.get("slip_net") or 0)
		row["item_amount"] = _js_round(row.get("item_amount") or 0)
		row["item_tax"] = _js_round(row.get("item_tax") or 0)
		row["item_net"] = _js_round(row.get("item_net") or 0)

	return rows

@frappe.whitelist()
def get_salary_chart(year: int | None = None):
	"""
	Trả về dữ liệu cho Highcharts:
	- categories: ["Tháng 1", ..., "Tháng 12"]
	- salary: tổng lương từng tháng (từ slip.tong_thu_nhap)
	- allowance: tổng phụ cấp từng tháng (từ item.amount)
	- total_salary_year, total_allowance_year: tổng cả năm
	"""

	employee = _get_employee_of_user()
	if not employee:
		return

	if not year:
		year = now_datetime().year

	params = {
		"employee": employee,
		"year": cint(year),
	}

	# --- 1) LƯƠNG THEO THÁNG (chỉ từ bảng chính, không join item) ---
	sql_salary = """
		SELECT
			slip.month,
			SUM(COALESCE(slip.tong_thu_nhap, 0)) AS salary
		FROM `tabVNT Salary Slip` AS slip
		WHERE slip.docstatus = 1
		  AND slip.year = %(year)s
		  AND slip.employee = %(employee)s
		GROUP BY slip.month
	"""

	# --- 2) PHỤ CẤP THEO THÁNG (từ bảng con) ---
	sql_allowance = """
	SELECT
		slip.month,
		SUM(COALESCE(item.tong, 0)) AS allowance
	FROM `tabVNT Salary Slip` AS slip
	LEFT JOIN `tabVNT Salary Slip Item` AS item
		ON item.parent = slip.name
	WHERE slip.docstatus = 1
	  AND slip.year = %(year)s
		  AND slip.employee = %(employee)s
		GROUP BY slip.month
	"""

	salary_rows = frappe.db.sql(sql_salary, params, as_dict=True)
	allow_rows = frappe.db.sql(sql_allowance, params, as_dict=True)

	monthly: dict[int, dict[str, float]] = {}

	# Gộp lương theo tháng
	for row in salary_rows:
		month_str = cstr(row.get("month") or "").strip()
		if not month_str:
			continue
		try:
			m = cint(month_str)
		except Exception:
			continue
		if not m:
			continue

		monthly.setdefault(m, {})
		monthly[m]["salary"] = row.get("salary") or 0

	# Gộp phụ cấp theo tháng
	for row in allow_rows:
		month_str = cstr(row.get("month") or "").strip()
		if not month_str:
			continue
		try:
			m = cint(month_str)
		except Exception:
			continue
		if not m:
			continue

		monthly.setdefault(m, {})
		monthly[m]["allowance"] = row.get("allowance") or 0

	categories: list[str] = []
	salary_values: list[float] = []
	allowance_values: list[float] = []

	for m in range(1, 13):
		categories.append(_("Tháng {0}").format(m))
		data = monthly.get(m, {})
		salary_values.append(data.get("salary", 0) or 0)
		allowance_values.append(data.get("allowance", 0) or 0)

	total_salary = sum(salary_values)
	total_allowance = sum(allowance_values)

	return {
		"year": cint(year),
		"categories": categories,
		"salary": salary_values,
		"allowance": allowance_values,
		"total_salary_year": total_salary,
		"total_allowance_year": total_allowance,
	}

def _round0(value):
	"""Làm tròn về số nguyên, không lấy phần thập phân."""
	return cint(flt(value or 0, 0))


def _safe_month(raw) -> int | None:
	month_str = cstr(raw or "").strip()
	if not month_str:
		return None
	try:
		m = cint(month_str)
	except Exception:
		return None
	return m if 1 <= m <= 12 else None


def _get_company_projected_month_salary(year: int, month: int, company: str | None) -> float:
	"""Tổng lương dự kiến tháng (gross tong_thu_nhap) cho toàn bộ nhân sự."""
	company = _resolve_company(company)
	employees = _get_company_active_employees(company)
	total = 0.0
	for emp in employees:
		gross = _get_gross_income_from_slip(emp["name"], month, year)
		# Nếu chưa có slip tháng này thì thử tạm tính net rồi dùng luôn (không có gross từ engine)
		if gross is None:
			net = _get_monthly_payroll_net_income(emp["name"], month, year, emp.get("company"))
			if net is not None:
				gross = net
		if gross is not None:
			total += flt(gross)
	return total


def _get_company_active_employees(company: str | None) -> list[dict]:
	filters = {"status": "Active"}
	if company:
		filters["company"] = company
	return frappe.db.get_all("Employee", filters=filters, fields=["name", "company"])


def _get_gross_income_from_slip(employee: str, month: int | str, year: int | str) -> float | None:
	"""Lấy tong_thu_nhap từ salary slip (có giải mã nếu cần)."""
	if not employee or not month or not year:
		return None

	month_str = f"{cint(month):02d}"
	rows = frappe.db.get_all(
		"VNT Salary Slip",
		filters={
			"docstatus": 1,
		"employee": employee,
		"year": cint(year),
		"month": month_str,
	},
		fields=["tong_thu_nhap", "tong_thu_nhap_encrypted"],
	)
	total = 0.0
	for row in rows:
		gross = row.get("tong_thu_nhap")
		if gross in (None, ""):
			decrypted = VNTSalarySlip.decrypt_salary_values(
				tong_thu_nhap_encrypted=row.get("tong_thu_nhap_encrypted")
			)
			gross = decrypted.get("tong_thu_nhap")
		if gross is not None:
			total += flt(gross)

	return total if total else None


def _get_company_annual_salary_fund(company: str | None) -> float:
	"""Lấy quỹ lương năm từ custom_annual_salary_fund của Company."""
	company = _resolve_company(company)
	if not company:
		return 0.0
	val = frappe.db.get_value("Company", company, "custom_annual_salary_fund")
	return flt(val)


def _resolve_company(company: str | None) -> str | None:
	"""Ưu tiên tham số, nếu không có thì suy ra từ nhân sự của user hiện tại."""
	if company:
		return company
	employee = _get_employee_of_user()
	if employee:
		return frappe.db.get_value("Employee", employee, "company")
	return None


@frappe.whitelist()
def get_company_salary_kpi(year: int | None = None,
						month: int | None = None,
						company: str | None = None):
	"""
	Trả về 4 KPI tổng của cả công ty trong VNT Salary Slip (docstatus = 1):

	- total_year_salary: TỔNG LƯƠNG DỰ KIẾN THÁNG ĐẾN HIỆN TẠI (tính tạm bằng _get_monthly_payroll_net_income cho từng nhân sự)
	- total_prev_month_salary: TỔNG LƯƠNG THÁNG TRƯỚC
	- total_allowance: TỔNG PHỤ CẤP ĐÃ CHI CẢ NĂM
	- total_paid_salary_from_year_start: TỔNG LƯƠNG ĐÃ CHI TỪ ĐẦU NĂM ĐẾN THÁNG HIỆN TẠI
	- total_to_date_salary: QUỸ LƯƠNG CÒN LẠI = quỹ lương năm (custom_annual_salary_fund) - lương đã chi (slip submit) - lương dự kiến tháng hiện tại
	"""

	now_dt = now_datetime()
	if year is None:
		year = now_dt.year
	if month is None:
		month = now_dt.month
	company = _resolve_company(company)

	prev_month = month - 1 if month > 1 else None

	item_subquery = """
		SELECT
			parent,
			SUM(COALESCE(amount, 0)) AS total_allowance_net
		FROM `tabVNT Salary Slip Item`
		GROUP BY parent
	"""

	params = {
		"year": year,
		"month": f"{month:02d}",
	}

	conditions = [
		"slip.docstatus = 1",
		"slip.year = %(year)s",
		"emp.branch = 'Văn phòng 1'",
	]

	if company:
		conditions.append("COALESCE(slip.company, emp.company) = %(company)s")
		params["company"] = company

	select_fields = [
		# 2. Tổng lương từ đầu năm đến tháng hiện tại
		"""
		SUM(
			CASE
				WHEN CAST(slip.month AS UNSIGNED) <= CAST(%(month)s AS UNSIGNED)
				THEN COALESCE(slip.tong_thu_nhap, 0)
				ELSE 0
			END
		) AS total_paid_salary
		""",

		# 3. Tổng phụ cấp cả năm
		"SUM(COALESCE(item.total_allowance_net, 0)) AS total_allowance",
	]

	# 4. Tổng lương tháng trước
	if prev_month:
		params["prev_month"] = f"{prev_month:02d}"
		select_fields.append(
			"""
			SUM(
				CASE
					WHEN slip.month = %(prev_month)s
					THEN COALESCE(slip.tong_thu_nhap, 0)
					ELSE 0
				END
			) AS total_prev_month_salary
			"""
		)
	else:
		select_fields.append("0 AS total_prev_month_salary")

	sql = f"""
		SELECT
			{", ".join(select_fields)}
		FROM `tabVNT Salary Slip` AS slip
		LEFT JOIN `tabEmployee` AS emp ON emp.name = slip.employee
		LEFT JOIN ({item_subquery}) AS item ON item.parent = slip.name
		WHERE {" AND ".join(conditions)}
	"""

	res = frappe.db.sql(sql, params, as_dict=True)
	row = res[0] if res else {}

	# Tổng lương dự kiến (tháng hiện tại) tính trực tiếp từ payroll engine
	projected_month_salary = _get_company_projected_month_salary(year, month, company)
	total_paid_salary = flt(row.get("total_paid_salary"))
	salary_fund = _get_company_annual_salary_fund(company)
	# frappe.throw("a "+_round0(salary_fund))

	total_to_date_salary = salary_fund - total_paid_salary - projected_month_salary
	return {
		"year": year,
		"month": month,
		"previous_month": prev_month,
		"company": company or "",

		# LÀM TRÒN 0 DECIMAL Ở ĐÂY
		"total_year_salary": _round0(projected_month_salary),
		"total_prev_month_salary": _round0(row.get("total_prev_month_salary")),
		"total_allowance": _round0(row.get("total_allowance")),
		"total_paid_salary_from_year_start": _round0(total_paid_salary),
		"total_to_date_salary": _round0(total_to_date_salary),
	}

@frappe.whitelist()
def get_company_salary_chart(year: int | None = None,
							company: str | None = None):
	"""
	Chart tổng của CÔNG TY (giống get_salary_chart nhưng aggregate theo company):

	- categories: ["Tháng 1", ..., "Tháng 12"]
	- salary: tổng lương từng tháng (từ slip.tong_thu_nhap)
	- allowance: tổng phụ cấp từng tháng (từ item.amount)
	- total_salary_year, total_allowance_year: tổng cả năm của CÔNG TY
	"""

	# Lấy employee để suy ra company nếu không truyền
	if not year:
		year = now_datetime().year

	year = cint(year)

	company = _resolve_company(company)
	if not company:
		return

	params = {
		"year": year,
		"company": company,
	}

	# --- 1) LƯƠNG THEO THÁNG CHO CẢ CÔNG TY ---
	sql_salary = """
		SELECT
			slip.month,
			slip.tong_thu_nhap,
			slip.thuc_linh,
			slip.tong_thu_nhap_encrypted,
			slip.thuc_linh_encrypted
		FROM `tabVNT Salary Slip` AS slip
		LEFT JOIN `tabEmployee` AS emp ON emp.name = slip.employee
		WHERE slip.docstatus = 1
		  AND slip.year = %(year)s
		  AND COALESCE(slip.company, emp.company) = %(company)s
		  AND emp.branch = 'Văn phòng 1'
	"""
	salary_rows = frappe.db.sql(sql_salary, params, as_dict=True)
	# --- 2) PHỤ CẤP THEO THÁNG CHO CẢ CÔNG TY ---
	sql_allowance = """
		SELECT
			slip.month,
			SUM(COALESCE(item.tong, 0)) AS allowance
		FROM `tabVNT Salary Slip` AS slip
		LEFT JOIN `tabVNT Salary Slip Item` AS item
			ON item.parent = slip.name
		LEFT JOIN `tabEmployee` AS emp ON emp.name = slip.employee
		WHERE slip.docstatus = 1
		  AND slip.year = %(year)s
		  AND COALESCE(slip.company, emp.company) = %(company)s
		  AND emp.branch = 'Văn phòng 1'
		GROUP BY slip.month
	"""

	allow_rows = frappe.db.sql(sql_allowance, params, as_dict=True)

	monthly: dict[int, dict[str, float]] = {}

	# Gộp lương theo tháng
	for row in salary_rows:
		m = _safe_month(row.get("month"))
		if not m:
			continue
		monthly.setdefault(m, {})
		gross, _net = _get_salary_values_with_fallback(row)
		monthly[m]["salary"] = monthly[m].get("salary", 0) + gross

	# Gộp phụ cấp theo tháng
	for row in allow_rows:
		month_str = cstr(row.get("month") or "").strip()
		if not month_str:
			continue
		try:
			m = cint(month_str)
		except Exception:
			continue
		if not m:
			continue

		monthly.setdefault(m, {})
		monthly[m]["allowance"] = row.get("allowance") or 0

	categories: list[str] = []
	salary_values: list[float] = []
	allowance_values: list[float] = []

	for m in range(1, 13):
		categories.append(_("Tháng {0}").format(m))
		data = monthly.get(m, {})
		# dùng _round0 để không lấy phần thập phân
		salary_values.append(_round0(data.get("salary", 0)))
		allowance_values.append(_round0(data.get("allowance", 0)))

	total_salary = _round0(sum(salary_values))
	total_allowance = _round0(sum(allowance_values))

	return {
		"year": year,
		"company": company or "",
		"categories": categories,
		"salary": salary_values,
		"allowance": allowance_values,
		"total_salary_year": total_salary,
		"total_allowance_year": total_allowance,
	}
