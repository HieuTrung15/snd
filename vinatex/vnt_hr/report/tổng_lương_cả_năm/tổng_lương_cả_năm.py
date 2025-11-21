# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime,cstr


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

@frappe.whitelist()
def _get_data(filters: dict):
	conditions = ["slip.docstatus = 1", "slip.year = %(year)s"]
	params = {
		"year": filters["year"],
		"month": f"{filters['month']:02d}",
	}

	current_month_case = """
			SUM(CASE WHEN slip.month = %(month)s THEN COALESCE(slip.thuc_linh, 0) ELSE 0 END) AS current_month_net_income,
	"""

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

	return {
		# 4 KPI
		"year_to_date_net": row.get("year_to_date_net") or 0,
		"previous_month_salary": row.get("previous_month_salary") or 0,
		"previous_month_allowance": row.get("previous_month_allowance") or 0,
		"current_month_salary": row.get("current_month_salary") or 0,
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
