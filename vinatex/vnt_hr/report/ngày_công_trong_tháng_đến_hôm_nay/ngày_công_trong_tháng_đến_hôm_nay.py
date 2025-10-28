# -*- coding: utf-8 -*-
import json

import frappe
from frappe.utils import add_days, cint, get_first_day, get_last_day, getdate, today

from vinatex.vnt_hr.report.attendance_month_common import (
	compute_employee_month_context,
	fetch_employee_doc,
)
from vinatex.vnt_hr.report.tổng_hợp_chấm_công_tháng.tổng_hợp_chấm_công_tháng import STATUS_CODE

LEGEND_HTML = (
	"<div style='margin-top:8px;'>"
	"<strong>Chú thích:</strong> "
	"<span><strong>CV</strong>: Chưa vào làm; </span>"
	"<span><strong>L</strong>: Nghỉ lễ; </span>"
	"<span><strong>T</strong>: Cuối tuần; </span>"
	"<span><strong>X</strong>: Đi làm; </span>"
	"<span><strong>V</strong>: Vắng mặt; </span>"
	"<span><strong>O</strong>: Quên chấm công; </span>"
	"<span><strong>P</strong>: Nghỉ phép; </span>"
	"<span><strong>Ro</strong>: Nghỉ không lương; </span>"
	"<span><strong>CĐ</strong>: Nghỉ hưởng chế độ; </span>"
	"<span><strong>BH</strong>: Nghỉ BHXH; </span>"
	"<span><strong>CT</strong>: Đi công tác; </span>"
	"<span><strong>N1/2</strong>: Nghỉ nửa ngày.</span>"
	"</div>"
)


def execute(filters=None):
	"""
	Báo cáo ngày công trong tháng đến hôm nay.
	Giữ nguyên khung hiển thị nhưng sử dụng cùng logic phân loại với báo cáo
	“Tổng hợp chấm công tháng”.
	"""
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
	columns = _build_columns(days)
	day_details = context["day_details"]
	totals = context["totals"]
	category_totals = context["category_totals"]
	manual_flag = context["manual_flag"]

	row = {
		"value": None if context["value_units"] is None else float(context["value_units"]),
		"employee": employee,
		"employee_name": emp_doc.get("employee_name") or employee,
		"department": emp_doc.get("department"),
		"company": company,
	}

	for day in days:
		detail = day_details.get(day)
		fieldname = f"d{day.day:02d}"
		row[fieldname] = _display_code(detail)

	row["tot_present"] = _safe_number(totals.get("tot_present"), as_int=True)
	row["tot_leave"] = _safe_number(totals.get("tot_leave"), as_int=True)
	row["tot_holiday"] = _safe_number(totals.get("tot_holiday"), as_int=True)
	row["tot_weekend"] = _safe_number(totals.get("tot_weekend"), as_int=True)
	row["tot_absent"] = _safe_number(totals.get("tot_absent"), as_int=True)
	row["tot_miss"] = _safe_number(totals.get("tot_miss"), as_int=True)
	row["tot_on_duty"] = _safe_number(totals.get("tot_business_trip"))
	row["tot_unpaid_leave"] = (
		None if manual_flag else float(category_totals.get("unpaid", 0.0))
	)
	row["tot_paid_leave"] = (
		None if manual_flag else float(category_totals.get("paid_leave", 0.0))
	)
	row["tot_social_leave"] = (
		None if manual_flag else float(category_totals.get("regime", 0.0))
	)
	row["tot_half_day"] = _safe_number(totals.get("tot_half_day"), as_int=True)
	row["tot_not_joined"] = _safe_number(totals.get("tot_not_joined"), as_int=True)

	return columns, [row], LEGEND_HTML


def _display_code(detail):
	if not detail:
		return ""
	if detail.is_future:
		return ""
	if detail.status_key == "missing":
		return "O"
	if detail.status == STATUS_CODE["NGHỈ NỬA NGÀY"]:
		if detail.half_day_reason == "leave":
			code = _leave_code_for_category(detail.leave_category, detail.leave_type)
			return f"{code}(0.5)"
		return "N1/2"
	if detail.status == STATUS_CODE["CÔNG TÁC"]:
		units = detail.business_trip_units or 0.0
		if 0 < units < 1:
			return "CT(0.5)"
	if detail.status == STATUS_CODE["NGHỈ PHÉP"]:
		return _leave_code_for_category(detail.leave_category, detail.leave_type)
	return detail.status or ""


def _safe_number(value, as_int=False):
	if value is None:
		return None
	return int(value) if as_int else float(value)


def _leave_code_for_category(category, leave_type):
	if category == "unpaid":
		return "Ro"
	if category == "regime":
		text = (leave_type or "").lower()
		if any(keyword in text for keyword in ["bhxh", "ốm", "om", "sick"]):
			return "BH"
		return "CĐ"
	return "P"


def _columns():
	return [{
		"label": "Tổng số ngày công đã đi làm trong tháng",
		"fieldname": "value",
		"fieldtype": "Float",
		"width": 150,
	}]


def _build_columns(days):
	columns = _columns() + [
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
			"width": 160,
		},
		{
			"label": "Công ty",
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 160,
		},
	]

	for day in days:
		columns.append({
			"label": f"{day.day:02d}",
			"fieldname": f"d{day.day:02d}",
			"fieldtype": "Data",
			"width": 50,
		})

	columns.extend([
		{"fieldname": "tot_present", "label": "Đi làm", "fieldtype": "Int", "width": 80},
		{"fieldname": "tot_leave", "label": "Nghỉ phép", "fieldtype": "Int", "width": 90},
		{"fieldname": "tot_holiday", "label": "Nghỉ lễ", "fieldtype": "Int", "width": 80},
		{"fieldname": "tot_weekend", "label": "Cuối tuần", "fieldtype": "Int", "width": 90},
		{"fieldname": "tot_absent", "label": "Vắng", "fieldtype": "Int", "width": 70},
		{"fieldname": "tot_miss", "label": "Quên CC", "fieldtype": "Int", "width": 80},
		{"fieldname": "tot_on_duty", "label": "Công tác", "fieldtype": "Float", "width": 90},
		{"fieldname": "tot_unpaid_leave", "label": "Nghỉ K/L", "fieldtype": "Float", "width": 90},
		{"fieldname": "tot_paid_leave", "label": "Nghỉ hưởng lương", "fieldtype": "Float", "width": 130},
		{"fieldname": "tot_social_leave", "label": "Nghỉ BHXH", "fieldtype": "Float", "width": 95},
		{"fieldname": "tot_half_day", "label": "Nửa ngày", "fieldtype": "Int", "width": 90},
		{"fieldname": "tot_not_joined", "label": "Chưa vào làm", "fieldtype": "Int", "width": 110},
	])
	return columns


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
	if filters.get("from_date"):
		start = getdate(filters["from_date"])
		end = getdate(filters.get("to_date") or start)
		return start, end

	ref_date = getdate(today())
	month = cint(filters.get("month") or 0)
	year = cint(filters.get("year") or 0)
	if month and year:
		start = get_first_day(getdate(f"{year:04d}-{month:02d}-01"))
	else:
		start = get_first_day(ref_date)
	return start, get_last_day(start)
