# -*- coding: utf-8 -*-
import json

import frappe
from frappe.utils import add_days, cint, get_first_day, get_last_day, getdate, today

from vinatex.vnt_hr.report.attendance_month_common import (
	compute_employee_month_context,
	fetch_employee_doc,
)
LEGEND_HTML = (
	"<div style='margin-top:8px;'>"
	"<strong>Chú thích:</strong> "
	"<span><strong>BT</strong>: Bất thường (không có chấm công/đơn hợp lệ). </span>"
	"</div>"
)


def execute(filters=None):
	filters = _parse_filters(filters)

	employee = filters.get("employee") or _employee_from_session()
	if not employee:
		return _columns(), [{"value": 0.0}], LEGEND_HTML

	start_date, end_date = _resolve_period(filters)
	if cint(filters.get("to_today") or 0):
		end_date = min(end_date, getdate(add_days(today(), -1)))
	if end_date < start_date:
		return _columns(), [{"value": 0.0}], LEGEND_HTML

	emp_doc = fetch_employee_doc(employee)
	if not emp_doc:
		return _columns(), [{"value": 0.0}], LEGEND_HTML

	company = (
		filters.get("company")
		or emp_doc.get("company")
		or frappe.defaults.get_user_default("Company")
		or frappe.defaults.get_global_default("company")
	)

	context = compute_employee_month_context(emp_doc, start_date, end_date, company)
	if not context:
		return _columns(), [{"value": 0.0}], LEGEND_HTML

	days = context["days"]
	day_details = context["day_details"]
	totals = context["totals"]

	columns = _columns() + _info_columns() + _day_columns(days)

	row = {
		"employee": employee,
		"employee_name": emp_doc.get("employee_name") or employee,
		"department": emp_doc.get("department"),
		"company": company,
	}

	for day in days:
		detail = day_details.get(day)
		fieldname = f"d{day.day:02d}"
		row[fieldname] = _display_codes(detail)

	row["value"] = _safe_float(totals.get("tot_miss"))

	return columns, [row], LEGEND_HTML


def _display_codes(detail):
	if not detail or detail.is_future:
		return ""

	if detail.status_key == "missing":
		return "BT"

	return ""


def _safe_float(value):
	if value is None:
		return None
	return float(value)


def _columns():
	return [{
		"label": "Số ngày chấm công bất thường",
		"fieldname": "value",
		"fieldtype": "Float",
		"width": 200,
	}]


def _info_columns():
	return [
		{
			"label": "Mã NV",
			"fieldname": "employee",
			"fieldtype": "Link",
			"options": "Employee",
			"width": 110,
		},
		{
			"label": "Tên nhân viên",
			"fieldname": "employee_name",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": "Phòng ban",
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"width": 150,
		},
		{
			"label": "Công ty",
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 160,
		},
	]


def _day_columns(days):
	return [
		{
			"label": f"{d.day:02d}",
			"fieldname": f"d{d.day:02d}",
			"fieldtype": "Data",
			"width": 55,
		}
		for d in days
	]


def _parse_filters(filters):
	if isinstance(filters, str):
		try:
			filters = frappe.parse_json(filters)
		except Exception:
			try:
				filters = json.loads(filters)
			except Exception:
				filters = {}
	return filters or {}


def _employee_from_session():
	row = frappe.db.sql(
		"""
		SELECT name FROM `tabEmployee`
		WHERE user_id = %s AND status = 'Active'
		LIMIT 1
		""",
		(frappe.session.user,),
	)
	return row[0][0] if row else None


def _resolve_period(filters):
	if filters.get("from_date") and filters.get("to_date"):
		return getdate(filters["from_date"]), getdate(filters["to_date"])

	ref_date = getdate(add_days(today(), -1))
	month = cint(filters.get("month") or 0)
	year = cint(filters.get("year") or 0)
	if month and year:
		start = get_first_day(getdate(f"{year:04d}-{month:02d}-01"))
	else:
		start = get_first_day(ref_date)
	end = get_last_day(start)
	return start, min(end, ref_date)
