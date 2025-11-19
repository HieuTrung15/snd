from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

PRIVILEGED_ROLES = {"System Manager"}
MONTH_KEYS = [f"{idx:02d}" for idx in range(1, 13)]


def execute(filters=None):
	filters = _prepare_filters(filters or {})
	columns = _get_columns()
	data = _get_data(filters)
	return columns, data


def _prepare_filters(incoming_filters: dict) -> dict:
	prepared = dict(incoming_filters or {})

	if not prepared.get("year"):
		prepared["year"] = now_datetime().year

	prepared["year"] = cint(prepared["year"])
	if not prepared["year"]:
		frappe.throw(_("Vui lòng chọn Năm hợp lệ."))

	if _is_privileged_user():
		if prepared.get("employee"):
			prepared["employee"] = prepared["employee"].strip()
		else:
			prepared["employee"] = _get_employee_of_user()
	else:
		prepared["employee"] = _get_employee_of_user()

	if not prepared.get("employee"):
		frappe.throw(_("Tài khoản của bạn chưa được liên kết với hồ sơ nhân sự nào. Vui lòng liên hệ Ban QLNNL."))

	return prepared


def _is_privileged_user() -> bool:
	if frappe.session.user == "Administrator":
		return True
	roles = set(frappe.get_roles(frappe.session.user))
	return bool(roles & PRIVILEGED_ROLES)


def _get_employee_of_user() -> str | None:
	return frappe.db.get_value(
		"Employee",
		{"user_id": frappe.session.user, "status": "Active"},
		"name",
	)


def _get_columns():
	columns = [
		{"label": _("Mã nhân sự"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 140},
	]
	for idx, key in enumerate(MONTH_KEYS, start=1):
		columns.append(
			{"label": _("Tháng {0}").format(idx), "fieldname": f"month_{key}", "fieldtype": "Currency", "width": 130}
		)
	return columns


def _get_data(filters: dict):
	conditions = ["slip.docstatus = 1", "slip.year = %(year)s"]
	params = {
		"year": filters["year"],
	}

	if filters.get("employee"):
		conditions.append("slip.employee = %(employee)s")
		params["employee"] = filters["employee"]

	where_clause = " AND ".join(conditions)
	sql = f"""
		SELECT
			slip.employee,
			slip.month,
			COALESCE(slip.tong_thu_nhap, 0) AS tong_thu_nhap
		FROM `tabVNT Salary Slip` AS slip
		WHERE {where_clause}
		ORDER BY slip.employee, slip.month
	"""

	results = frappe.db.sql(sql, params, as_dict=True)
	rows_by_employee: dict[str, dict] = {}

	for entry in results:
		employee = entry.get("employee")
		month = entry.get("month")
		if not employee or not month:
			continue

		if employee not in rows_by_employee:
			rows_by_employee[employee] = {"employee": employee}
			for month_key in MONTH_KEYS:
				rows_by_employee[employee][f"month_{month_key}"] = 0

		month_key = f"month_{month}"
		if month_key not in rows_by_employee[employee]:
			continue

		rows_by_employee[employee][month_key] += entry.get("tong_thu_nhap", 0) or 0

	if not rows_by_employee:
		return []
	return [rows_by_employee[key] for key in sorted(rows_by_employee)]
