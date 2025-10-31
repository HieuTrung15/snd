# -*- coding: utf-8 -*-
import json

import frappe
from frappe.utils import add_days, cint, get_first_day, get_last_day, getdate, today

from vinatex.vnt_hr.report.attendance_month_common import (
	compute_employee_month_context,
	fetch_employee_doc,
)
from vinatex.vnt_hr.report.tổng_hợp_chấm_công_tháng.tổng_hợp_chấm_công_tháng import STATUS_CODE

SUMMARY_COLUMNS = [
	{"fieldname": "tot_business_trip", "label": "Công tác", "fieldtype": "Float", "width": 90},
	{"fieldname": "tot_annual_leave", "label": "Nghỉ phép", "fieldtype": "Float", "width": 100},
	{"fieldname": "tot_total", "label": "Tổng", "fieldtype": "Float", "width": 80},
]

LEGEND_HTML = (
	"<div style='margin-top:8px;'>"
	"<strong>Chú thích:</strong> "
	"<span><strong>CT</strong>: Ngày đi công tác; </span>"
	"<span><strong>P</strong>: Nghỉ phép; </span>"
	"</div>"
)


def execute(filters=None):
	filters = _parse_filters(filters)

	employee = filters.get("employee") or _employee_from_session()
	if not employee:
		return _columns(), [{"value": 0.0}], LEGEND_HTML

	start_date, end_date = _resolve_period(filters)
	ref_date = getdate(add_days(today(), -1))
	end_date = min(end_date, ref_date)
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
	manual_flag = context["manual_flag"]

	columns = _columns() + _info_columns() + _day_columns(days) + SUMMARY_COLUMNS

	tot_business_trip = 0.0
	tot_paid_leave = 0.0

	row = {
		"employee": employee,
		"employee_name": emp_doc.get("employee_name") or employee,
		"department": emp_doc.get("department"),
		"company": company,
	}

	for day in days:
		detail = day_details.get(day)
		fieldname = f"d{day.day:02d}"
		labels = []

		if detail and not detail.is_future:
			business_units = detail.business_trip_units or 0.0
			if detail.status == STATUS_CODE["CÔNG TÁC"] and business_units > 0:
				label = "CT" if business_units >= 1 else "CT(0.5)"
				labels.append(label)
				tot_business_trip += business_units

			if detail.leave_category == "paid_leave" and (detail.leave_units or 0.0) > 0:
				units = detail.leave_units or 0.0
				if detail.status == STATUS_CODE["NGHỈ NỬA NGÀY"] and detail.half_day_reason == "leave":
					labels.append("P(0.5)")
				else:
					labels.append("P" if units >= 1 else "P(0.5)")
				tot_paid_leave += units

		row[fieldname] = "/".join(labels) if labels else ""

	total_value = tot_business_trip + tot_paid_leave
	row["tot_business_trip"] =  float(tot_business_trip)
	row["tot_annual_leave"] =  float(tot_paid_leave)
	row["tot_total"] =  float(total_value)
	row["value"] =  float(total_value)

	return columns, [row], LEGEND_HTML


def _columns():
	return [{
		"label": "Số ngày nghỉ (Công tác + Phép năm)",
		"fieldname": "value",
		"fieldtype": "Float",
		"width": 180,
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
			"width": 140,
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
			"width": 50,
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

	ref_date = getdate(today())
	month = cint(filters.get("month") or 0)
	year = cint(filters.get("year") or 0)
	if month and year:
		start = get_first_day(getdate(f"{year:04d}-{month:02d}-01"))
	else:
		start = get_first_day(ref_date)
	return start, get_last_day(start)
