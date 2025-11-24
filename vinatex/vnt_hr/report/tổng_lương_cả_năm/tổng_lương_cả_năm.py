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
	params = {
		"year": filters["year"],
		"month": f"{filters['month']:02d}",
	}

	current_month_case = "0 AS current_month_net_income,"

	prev_month = filters.get("previous_month")
	if prev_month:
		params["prev_month"] = f"{prev_month:02d}"
		previous_month_case = """
			SUM(CASE WHEN slip.month = %(prev_month)s THEN COALESCE(slip.thuc_linh, 0) ELSE 0 END) AS previous_month_net_income,
		"""
	else:
		previous_month_case = "0 AS previous_month_net_income,"

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
			slip.employee,
			COALESCE(emp.employee_name, slip.employee) AS employee_name,
			emp.company,
			emp.department,
			slip.year,
			{current_month_case}
			{previous_month_case}
			COUNT(DISTINCT slip.month) AS salary_month_count,
			SUM(COALESCE(slip.tong_thu_nhap, 0)) AS total_gross_income,
			SUM(COALESCE(item.total_allowance, 0)) AS total_allowance,
			SUM(COALESCE(slip.thue_tncn, 0) + COALESCE(slip.thue_tncn_nam_truoc, 0)) AS total_income_tax,
			SUM(COALESCE(item.total_allowance_tax, 0)) AS total_allowance_tax,
			SUM(COALESCE(slip.thuc_linh, 0)) AS total_net_income,
			SUM(COALESCE(item.total_allowance_net, 0)) AS total_allowance_net
		FROM `tabVNT Salary Slip` AS slip
		LEFT JOIN `tabEmployee` AS emp ON emp.name = slip.employee
		LEFT JOIN ({item_subquery}) AS item ON item.parent = slip.name
		WHERE {where_clause}
		GROUP BY slip.employee, slip.year, emp.employee_name, emp.company, emp.department
		ORDER BY slip.employee, slip.year
	"""

	results = frappe.db.sql(sql, params, as_dict=True)
	for row in results:
		row["employee_name"] = row.get("employee_name") or row.get("employee")
		row["company"] = row.get("company") or ""
		row["department"] = row.get("department") or ""
		current_month_net = _get_monthly_payroll_net_income(
			row.get("employee"),
			filters.get("month"),
			filters.get("year"),
			row.get("company"),
		)
		row["current_month_net_income"] = current_month_net if current_month_net is not None else 0
	return results

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
			SUM(COALESCE(amount, 0)) AS total_allowance_net
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
			SUM(COALESCE(item.amount, 0)) AS allowance
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


@frappe.whitelist()
def get_company_salary_kpi(year: int | None = None,
                           month: int | None = None,
                           company: str | None = None):
    """
    Trả về 4 KPI tổng của cả công ty trong VNT Salary Slip (docstatus = 1):

    - total_year_salary: Tổng lương cả năm
    - total_prev_month_salary: Tổng lương tháng trước
    - total_allowance: Tổng phụ cấp cả năm
    - total_to_date_salary: Tổng lương từ đầu năm đến tháng hiện tại
    """

    now_dt = now_datetime()
    if year is None:
        year = now_dt.year
    if month is None:
        month = now_dt.month

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
    ]

    if company:
        conditions.append("slip.company = %(company)s")
        params["company"] = company

    select_fields = [
        # 1. Tổng lương cả năm
        "SUM(COALESCE(slip.tong_thu_nhap, 0)) AS total_year_salary",

        # 2. Tổng lương từ đầu năm đến tháng hiện tại
        """
        SUM(
            CASE
                WHEN CAST(slip.month AS UNSIGNED) <= CAST(%(month)s AS UNSIGNED)
                THEN COALESCE(slip.tong_thu_nhap, 0)
                ELSE 0
            END
        ) AS total_to_date_salary
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
        LEFT JOIN ({item_subquery}) AS item ON item.parent = slip.name
        WHERE {" AND ".join(conditions)}
    """

    res = frappe.db.sql(sql, params, as_dict=True)
    row = res[0] if res else {}

    return {
        "year": year,
        "month": month,
        "previous_month": prev_month,
        "company": company or "",

        # LÀM TRÒN 0 DECIMAL Ở ĐÂY
        "total_year_salary": _round0(row.get("total_year_salary")),
        "total_prev_month_salary": _round0(row.get("total_prev_month_salary")),
        "total_allowance": _round0(row.get("total_allowance")),
        "total_to_date_salary": _round0(row.get("total_to_date_salary")),
    }