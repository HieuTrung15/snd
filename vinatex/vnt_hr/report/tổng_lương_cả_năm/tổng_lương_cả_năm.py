# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime


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
        frappe.throw(_("Tài khoản của bạn chưa được liên kết với hồ sơ nhân sự nào."))

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
            SUM(COALESCE(thuc_linh, 0)) AS total_allowance_net
        FROM `tabVNT Salary Slip Item`
        GROUP BY parent
    """

    select_fields = [
        # Thực lĩnh từ đầu năm
        "SUM(COALESCE(slip.thuc_linh, 0)) AS year_to_date_net",
        # Lương tháng hiện tại
        "SUM(CASE WHEN slip.month = %(month)s THEN COALESCE(slip.thuc_linh, 0) ELSE 0 END) AS current_month_salary",
    ]

    prev_month = ym["previous_month"]
    if prev_month:
        params["prev_month"] = f"{prev_month:02d}"
        select_fields.append(
            "SUM(CASE WHEN slip.month = %(prev_month)s THEN COALESCE(slip.thuc_linh, 0) ELSE 0 END) AS previous_month_salary"
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