from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import cint, cstr, now_datetime

PRIVILEGED_ROLES = {"System Manager"}
DEFAULT_MONTH_KEYS = [f"{idx:02d}" for idx in range(1, 13)]
MONTH_FIELD_PREFIX = "month_"
MONTH_ALLOWANCE_SUFFIX = "_allowance"
SPECIAL_PAYOUT_OTHER_KEY = "__other__"
SPECIAL_PAYOUT_CONFIG = (
	{"key": "T13", "fieldname": "special_month_t13", "label_key": "Lương tháng 13"},
	{"key": "AL", "fieldname": "special_month_al", "label_key": "Lương tháng âm lịch"},
	{"key": SPECIAL_PAYOUT_OTHER_KEY, "fieldname": "special_month_other", "label_key": "Lương tháng khác"},
)


def execute(filters=None):
	filters = _prepare_filters(filters or {})
	month_definitions = _get_month_definitions(filters)
	special_definitions = _get_special_month_definitions()
	columns = _get_columns(month_definitions, special_definitions)
	data, chart = _get_data(filters, month_definitions, special_definitions)
	return columns, data, None, chart


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


def _get_columns(month_definitions: list[dict], special_definitions: list[dict]):
	columns = [
		{"label": _("Mã nhân sự"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 140},
	]
	for month in month_definitions:
		columns.append(
			{
				"label": month["label"],
				"fieldname": month["fieldname"],
				"fieldtype": "Currency",
				"width": 130,
			}
		)
		columns.append(
			{
				"label": f"{month['label']} - {_('Phụ cấp')}",
				"fieldname": month["allowance_fieldname"],
				"fieldtype": "Currency",
				"width": 130,
			}
		)
	for special in special_definitions:
		columns.append(
			{
				"label": special["label"],
				"fieldname": special["fieldname"],
				"fieldtype": "Currency",
				"width": 150,
			}
		)
	return columns


def _get_data(filters: dict, month_definitions: list[dict], special_definitions: list[dict]):
	conditions = ["slip.docstatus = 1", "slip.year = %(year)s"]
	params = {
		"year": filters["year"],
	}

	if filters.get("employee"):
		conditions.append("slip.employee = %(employee)s")
		params["employee"] = filters["employee"]

	where_clause = " AND ".join(conditions)
	allowance_subquery = """
		SELECT
			parent,
			SUM(COALESCE(tong, 0)) AS total_allowance
		FROM `tabVNT Salary Slip Item`
		GROUP BY parent
	"""
	sql = f"""
		SELECT
			slip.name,
			slip.employee,
			slip.month,
			COALESCE(slip.tong_thu_nhap, 0) AS tong_thu_nhap,
			COALESCE(item.total_allowance, 0) AS tong_phu_cap
		FROM `tabVNT Salary Slip` AS slip
		LEFT JOIN ({allowance_subquery}) AS item ON item.parent = slip.name
		WHERE {where_clause}
		ORDER BY slip.employee, slip.month
	"""

	results = frappe.db.sql(sql, params, as_dict=True)
	rows_by_employee: dict[str, dict] = {}
	default_fieldnames: list[str] = []
	monthly_totals: dict[str, dict[str, float]] = {}
	for month in month_definitions:
		default_fieldnames.extend([month["fieldname"], month["allowance_fieldname"]])
		monthly_totals[month["fieldname"]] = {"salary": 0.0, "allowance": 0.0}
	default_fieldnames.extend(special["fieldname"] for special in special_definitions)

	for entry in results:
		employee = entry.get("employee")
		month = entry.get("month")
		if not employee or not month:
			continue

		row = _ensure_employee_row(rows_by_employee, employee, default_fieldnames)

		month_key = _make_month_fieldname(month)
		allowance_key = _make_month_allowance_fieldname(month)
		totals = monthly_totals.setdefault(month_key, {"salary": 0.0, "allowance": 0.0})

		if month_key in row:
			salary = entry.get("tong_thu_nhap", 0) or 0
			row[month_key] += salary
			totals["salary"] = totals.get("salary", 0) + salary
		if allowance_key in row:
			allowance = entry.get("tong_phu_cap", 0) or 0
			row[allowance_key] += allowance
			totals["allowance"] = totals.get("allowance", 0) + allowance

	special_totals = _get_special_salary_totals(filters, special_definitions)
	for employee, totals in special_totals.items():
		row = _ensure_employee_row(rows_by_employee, employee, default_fieldnames)
		for special in special_definitions:
			amount = totals.get(special["key"])
			if amount is None:
				continue
			row[special["fieldname"]] += amount

	rows = [rows_by_employee[key] for key in sorted(rows_by_employee)] if rows_by_employee else []
	chart = _build_chart_payload(month_definitions, monthly_totals)
	return rows, chart


def _get_month_definitions(filters: dict) -> list[dict]:
	definitions: list[dict] = []
	existing_values: set[str] = set()

	for value, label_hint in _get_month_field_options():
		month_def = _build_month_definition(value, label_hint)
		if not month_def or month_def["value"] in existing_values:
			continue
		definitions.append(month_def)
		existing_values.add(month_def["value"])

	if not definitions:
		for idx, key in enumerate(DEFAULT_MONTH_KEYS, start=1):
			month_def = {
				"value": key,
				"label": _("Tháng {0}").format(idx),
				"fieldname": _make_month_fieldname(key),
				"allowance_fieldname": _make_month_allowance_fieldname(key),
			}
			definitions.append(month_def)
			existing_values.add(key)

	for value in _get_distinct_months(filters):
		if not value or value in existing_values:
			continue
		month_def = _build_month_definition(value)
		if not month_def:
			continue
		definitions.append(month_def)
		existing_values.add(month_def["value"])

	return definitions


def _get_special_month_definitions() -> list[dict]:
	definitions = []
	for config in SPECIAL_PAYOUT_CONFIG:
		definitions.append(
			{
				"key": config["key"],
				"fieldname": config["fieldname"],
				"label": _(config["label_key"]),
			}
		)
	return definitions


def _ensure_employee_row(rows: dict[str, dict], employee: str, default_fieldnames: list[str]) -> dict:
	if employee not in rows:
		rows[employee] = _make_default_row(employee, default_fieldnames)
	return rows[employee]


def _make_default_row(employee: str, fieldnames: list[str]) -> dict:
	row = {"employee": employee}
	for fieldname in fieldnames:
		row[fieldname] = 0
	return row


def _get_month_field_options() -> list[tuple[str, str | None]]:
	meta = frappe.get_meta("VNT Salary Slip")
	field = meta.get_field("month") if meta else None
	if not field or not field.options:
		return []
	options = []
	for row in field.options.splitlines():
		value = row.strip()
		if not value:
			continue
		if "|" in value:
			label, actual_value = value.split("|", 1)
			label = label.strip() or None
			actual_value = actual_value.strip() or label
			options.append((cstr(actual_value), label))
		else:
			options.append((cstr(value), None))
	return options


def _get_special_salary_totals(filters: dict, special_definitions: list[dict]) -> dict[str, dict[str, float]]:
	if not special_definitions:
		return {}
	valid_keys = {entry["key"] for entry in special_definitions}
	conditions = ["parent.docstatus = 1", "parent.year = %(year)s"]
	params: dict[str, object] = {"year": filters["year"]}
	if filters.get("employee"):
		conditions.append("item.employee = %(employee)s")
		params["employee"] = filters["employee"]
	where_clause = " AND ".join(conditions)
	sql = f"""
		SELECT
			item.employee,
			parent.luong_thang,
			SUM(COALESCE(item.thu_nhap_thuc_linh, 0)) AS net_income
		FROM `tabVNT 13th Month Salary Item` AS item
		INNER JOIN `tabVNT 13th Month Salary` AS parent ON parent.name = item.parent
		WHERE {where_clause}
		GROUP BY item.employee, parent.luong_thang
	"""
	results = frappe.db.sql(sql, params, as_dict=True)
	totals: dict[str, dict[str, float]] = {}
	for row in results:
		employee = row.get("employee")
		if not employee:
			continue
		key = _normalize_special_key(row.get("luong_thang"), valid_keys)
		amount = row.get("net_income") or 0
		totals.setdefault(employee, {})
		totals[employee][key] = totals[employee].get(key, 0) + amount
	return totals


def _build_chart_payload(month_definitions: list[dict], monthly_totals: dict[str, dict[str, float]]) -> dict | None:
	if not month_definitions:
		return None
	labels: list[str] = []
	salary_values: list[float] = []
	allowance_values: list[float] = []

	for month in month_definitions:
		fieldname = month["fieldname"]
		totals = monthly_totals.get(fieldname, {})
		labels.append(month["label"])
		salary_values.append(totals.get("salary", 0))
		allowance_values.append(totals.get("allowance", 0))

	if not any(salary_values) and not any(allowance_values):
		return None

	return {
		"type": "axis-mixed",
		"data": {
			"labels": labels,
			"datasets": [
				{"name": _("Lương tháng"), "chartType": "bar", "values": salary_values},
				{"name": _("Phụ cấp"), "chartType": "line", "values": allowance_values},
			],
		},
		"height": 320,
	}


def _get_distinct_months(filters: dict) -> list[str]:
	conditions = ["docstatus = 1", "year = %(year)s"]
	params: dict[str, object] = {"year": filters["year"]}
	if filters.get("employee"):
		conditions.append("employee = %(employee)s")
		params["employee"] = filters["employee"]
	where_clause = " AND ".join(conditions)
	sql = f"""
		SELECT DISTINCT month
		FROM `tabVNT Salary Slip`
		WHERE {where_clause}
		ORDER BY month
	"""
	results = frappe.db.sql(sql, params)
	return [cstr(row[0]).strip() for row in results if row and row[0]]


def _normalize_special_key(value: str | None, valid_keys: set[str]) -> str:
	key = cstr(value or "").strip().upper()
	if key and key in valid_keys and key != SPECIAL_PAYOUT_OTHER_KEY:
		return key
	return SPECIAL_PAYOUT_OTHER_KEY


def _build_month_definition(value: str, label_hint: str | None = None) -> dict | None:
	value = cstr(value or "").strip()
	if not value:
		return None
	label = _get_month_label(value, label_hint)
	return {
		"value": value,
		"label": label,
		"fieldname": _make_month_fieldname(value),
		"allowance_fieldname": _make_month_allowance_fieldname(value),
	}


def _get_month_label(value: str, label_hint: str | None) -> str:
	if label_hint:
		return label_hint
	if value.isdigit():
		try:
			month_number = cint(value)
		except Exception:
			month_number = None
		else:
			if month_number:
				return _("Tháng {0}").format(month_number)
	return value


def _make_month_fieldname(value: str) -> str:
	safe_value = re.sub(r"\W+", "_", cstr(value or "").strip())
	safe_value = safe_value.strip("_") or "value"
	return f"{MONTH_FIELD_PREFIX}{safe_value.lower()}"


def _make_month_allowance_fieldname(value: str) -> str:
	return f"{_make_month_fieldname(value)}{MONTH_ALLOWANCE_SUFFIX}"
