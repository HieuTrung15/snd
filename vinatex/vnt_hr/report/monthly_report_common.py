"""Shared data preparation for the two HR monthly matrix reports.

The Excel workbooks supplied by HR are presentation templates only.  Values in
these reports always come from the current Employee, shift plan, Employee
Checkin, Attendance, Leave Application and VNT Attendance Confirm records.
"""

from __future__ import annotations

import json
import math
import unicodedata
from collections import OrderedDict
from datetime import date, datetime, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, today

from vinatex.vnt_hr.attendance_processing import (
	build_shift_windows,
	calculate_attendance_details,
	classify_work_date,
	load_checkins_for_windows,
	load_holiday_context,
)
from vinatex.vnt_hr.report.tổng_hợp_chấm_công_tháng.monthly_symbols import (
	_build_confirmation_review,
	_confirmation_applies,
	_get_attendance_map,
	_get_confirmation_map,
	_get_employees,
	_get_leave_map,
	_get_symbol,
)


REPORT_ROLES = {"System Manager", "HR User", "HR Manager"}
WORK_SYMBOLS = {"X", "S", "C", "Đ", "CT"}
ANOMALY_STATES = {
	"missing_in": {
		"label": "Không có giờ vào",
		"fill": "FFFF9900",
		"css": "#f59e0b",
	},
	"missing_out": {
		"label": "Không có giờ ra",
		"fill": "FFFFFF00",
		"css": "#fde047",
	},
	"absent": {
		"label": "Ngày phải đi làm nhưng không có chấm vân tay hợp lệ",
		"fill": "FFFF0000",
		"css": "#ef4444",
	},
}


def parse_filters(filters=None):
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except ValueError:
			frappe.throw(_("Điều kiện lọc báo cáo không hợp lệ."))
	filters = frappe._dict(filters or {})
	if not filters.get("company"):
		frappe.throw(_("Vui lòng chọn Công ty."))

	month = cint(filters.get("month")) or getdate(today()).month
	year = cint(filters.get("year")) or getdate(today()).year
	if month < 1 or month > 12 or year < 2000 or year > 2100:
		frappe.throw(_("Tháng hoặc năm không hợp lệ."))

	from_date = date(year, month, 1)
	to_date = date(year, month, _days_in_month(year, month))
	filters.month = f"{month:02d}"
	filters.year = year
	filters.from_date = from_date
	filters.to_date = to_date
	return filters


def validate_report_access():
	if frappe.session.user == "Administrator":
		return
	roles = set(frappe.get_roles())
	if REPORT_ROLES.intersection(roles) or {
		"Employee",
		"Employee Self Service",
	}.intersection(roles):
		return
	frappe.throw(_("Bạn không có quyền xem báo cáo chấm công này."), frappe.PermissionError)


def build_monthly_context(filters=None):
	"""Return one reviewed employee/day matrix used by both reports."""
	validate_report_access()
	filters = parse_filters(filters)
	from_date, to_date = filters.from_date, filters.to_date
	days = list(_date_range(from_date, to_date))
	employees = _get_employees(filters, from_date, to_date)
	_enrich_employees(employees)

	context = frappe._dict(
		filters=filters,
		company=filters.company,
		from_date=from_date,
		to_date=to_date,
		days=days,
		rows=[],
	)
	if not employees:
		return context

	windows = build_shift_windows(employees, from_date, to_date)
	planned_map, outside_map = load_checkins_for_windows(
		employees, windows, from_date, to_date
	)
	holiday_context = load_holiday_context(employees, windows, from_date, to_date)
	attendance_map = _get_attendance_map(employees, from_date, to_date)
	leave_map = _get_leave_map(employees, from_date, to_date)
	confirmation_map = _get_confirmation_map(employees, from_date, to_date)
	can_open_confirmation = bool(REPORT_ROLES.intersection(frappe.get_roles())) or (
		frappe.session.user == "Administrator"
	)
	effective_end = min(to_date, getdate(add_days(today(), -1)))

	for employee in employees:
		row = _new_employee_row(employee, from_date, to_date)
		row.can_open_confirmation = can_open_confirmation
		for work_date in days:
			day = _build_day_record(
				employee=employee,
				work_date=work_date,
				window=windows.get((employee.name, work_date)),
				planned_logs=planned_map.get((employee.name, work_date), []),
				outside_logs=outside_map.get((employee.name, work_date), []),
				holiday_context=holiday_context,
				attendance=attendance_map.get((employee.name, work_date)),
				leave=leave_map.get((employee.name, work_date)),
				confirmation=confirmation_map.get((employee.name, work_date)),
				can_open_confirmation=can_open_confirmation,
				effective_end=effective_end,
			)
			fieldname = f"d{work_date.day:02d}"
			row[fieldname] = day.symbol
			row[f"{fieldname}__state"] = day.state
			row[f"{fieldname}__label"] = day.label
			row[f"{fieldname}__confirmation"] = day.confirmation_name
			row[f"{fieldname}__review_state"] = day.review_state
			row[f"{fieldname}__review_label"] = day.review_label
			row[f"{fieldname}__overtime"] = day.overtime_hours
			row[f"{fieldname}__day_category"] = day.day_category
			_apply_attendance_totals(row, day)
			_apply_overtime_totals(row, day)
		context.rows.append(row)

	return context
@frappe.whitelist()
def ensure_attendance_confirmation(employee, work_date):
	"""Create/refresh the monthly confirmation and return the matching document.

	This is used only when an HR user clicks a coloured cell whose anomaly did
	not yet have a generated confirmation row.
	"""
	validate_report_access()
	if frappe.session.user != "Administrator" and not REPORT_ROLES.intersection(
		frappe.get_roles()
	):
		frappe.throw(_("Để mở phiếu giải trình cần có vai trò Nhân sự."), frappe.PermissionError)

	work_date = getdate(work_date)
	employee_row = frappe.db.get_value(
		"Employee",
		employee,
		["name", "company"],
		as_dict=True,
	)
	if not employee_row:
		frappe.throw(_("Không tìm thấy nhân viên."))

	month_start = work_date.replace(day=1)
	month_end = work_date.replace(
		day=_days_in_month(work_date.year, work_date.month)
	)
	effective_end = min(month_end, getdate(add_days(today(), -1)))
	if work_date > effective_end:
		frappe.throw(_("Chưa thể tạo giải trình cho ngày trong tương lai."))

	from vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm import (
		make_attendance_confirm,
	)

	make_attendance_confirm(
		from_date=month_start,
		to_date=effective_end,
		company=employee_row.company,
		employee=employee_row.name,
	)
	matching = frappe.db.sql(
		"""
		SELECT p.name
		FROM `tabVNT Attendance Confirm Item` i
		INNER JOIN `tabVNT Attendance Confirm` p ON p.name = i.parent
		WHERE p.docstatus < 2
		  AND p.employee = %(employee)s
		  AND i.date = %(work_date)s
		ORDER BY p.modified DESC, i.idx DESC
		LIMIT 1
		""",
		{"employee": employee_row.name, "work_date": work_date},
		as_dict=True,
	)
	if not matching:
		frappe.throw(
			_("Dữ liệu chấm công đã thay đổi; ô này không còn cần giải trình.")
		)
	return {"name": matching[0].name}


def group_rows(rows):
	grouped = OrderedDict()
	for row in rows:
		section = grouped.setdefault(row.section, OrderedDict())
		section.setdefault(row.subgroup or "", []).append(row)
	return grouped


def confirmation_url(document_name):
	if not document_name:
		return None
	from frappe.utils import get_url

	return get_url(f"/app/vnt-attendance-confirm/{document_name}")


def strip_accents(value):
	text = unicodedata.normalize("NFD", value or "")
	text = "".join(character for character in text if unicodedata.category(character) != "Mn")
	return text.replace("đ", "d").replace("Đ", "D")


def compact_number(value):
	value = float(value or 0)
	if value.is_integer():
		return int(value)
	return round(value, 2)


def excel_content_width(values, *, minimum=6, maximum=40, padding=2):
	"""Return a practical Excel width that fits the longest visible value."""
	longest = max(
		(len(str(value).replace("\n", " ")) for value in values if value not in (None, "")),
		default=0,
	)
	return min(maximum, max(minimum, longest + padding))


def _new_employee_row(employee, from_date, to_date):
	section, subgroup = _employee_section(employee)
	return frappe._dict(
		employee=employee.name,
		employee_name=employee.employee_name,
		employee_name_ascii=strip_accents(employee.employee_name),
		employee_code=(
			employee.get("custom_employee_code")
			or employee.get("employee_number")
			or employee.get("attendance_device_id")
			or employee.name
		),
		department=employee.get("department_display") or _short_department(employee.department),
		department_code=employee.get("department_code") or _department_code(employee.department),
		designation=employee.get("designation") or "",
		shift_label=_employee_shift_label(employee),
		section=section,
		subgroup=subgroup,
		from_date=from_date.isoformat(),
		to_date=to_date.isoformat(),
		tot_work_days=0.0,
		tot_work_hours=0.0,
		tot_sick=0.0,
		tot_night=0.0,
		tot_sunday=0.0,
		tot_holiday=0.0,
		tot_public_holiday=0.0,
		tot_special_leave=0.0,
		tot_paid_leave=0.0,
		tot_family_leave=0.0,
		tot_comp_leave=0.0,
		tot_unpaid_reason=0.0,
		tot_unpaid_no_reason=0.0,
		tot_overtime_normal=0.0,
		tot_overtime_off=0.0,
		tot_overtime_holiday=0.0,
		rating="",
		score="",
	)


def _build_day_record(
	*,
	employee,
	work_date,
	window,
	planned_logs,
	outside_logs,
	holiday_context,
	attendance,
	leave,
	confirmation,
	can_open_confirmation,
	effective_end,
):
	if work_date > effective_end:
		return _empty_day("future")
	joining_date = getdate(employee.date_of_joining) if employee.date_of_joining else date.min
	if work_date < joining_date:
		return _empty_day("not_joined")

	day_type = classify_work_date(employee, window, holiday_context)
	technical_symbol = _get_symbol(
		employee,
		window,
		planned_logs,
		outside_logs,
		attendance,
		leave,
		{},
		day_type,
	)
	review = None
	if _confirmation_applies(technical_symbol, day_type, confirmation):
		review = _build_confirmation_review(
			confirmation,
			include_document_name=can_open_confirmation,
		)

	details = None
	if window and planned_logs and not window.get("is_off"):
		details = calculate_attendance_details(
			window, planned_logs, respect_marking_flags=False
		)
	working_hours = float(details.working_hours or 0) if details else 0.0
	shift_symbol = _shift_symbol(window)
	state = _anomaly_state(technical_symbol, day_type)
	symbol, category, units = _attendance_symbol(
		employee=employee,
		work_date=work_date,
		day_type=day_type,
		window=window,
		shift_symbol=shift_symbol,
		technical_symbol=technical_symbol,
		attendance=attendance,
		leave=leave,
		holiday_context=holiday_context,
		working_hours=working_hours,
	)
	overtime_hours = _calculate_overtime_hours(
		employee=employee,
		day_type=day_type,
		window=window,
		planned_logs=planned_logs,
		outside_logs=outside_logs,
	)
	day_category = "holiday" if day_type == "holiday" else "off" if day_type == "off" else "normal"
	return frappe._dict(
		symbol=symbol,
		state=state,
		label=ANOMALY_STATES.get(state, {}).get("label", ""),
		confirmation_name=(review.document_name if review else None),
		review_state=(review.state if review else ""),
		review_label=(review.label if review else ""),
		technical_symbol=technical_symbol,
		category=category,
		units=units,
		working_hours=working_hours,
		overtime_hours=overtime_hours,
		day_category=day_category,
	)


def _attendance_symbol(
	*,
	employee,
	work_date,
	day_type,
	window,
	shift_symbol,
	technical_symbol,
	attendance,
	leave,
	holiday_context,
	working_hours,
):
	attendance_status = (attendance.status or "").strip() if attendance else ""
	leave_type = ""
	if attendance_status == "On Leave":
		leave_type = attendance.leave_type or ""
	elif leave:
		leave_type = leave.leave_type or ""
	if leave_type:
		return _leave_symbol(leave_type)
	if attendance_status == "Work Trip":
		return "CT", "work", 1.0
	if attendance_status == "Half Day" and attendance.leave_type:
		return "P", "paid_leave", 0.5

	parts = set((technical_symbol or "").split("/"))
	has_off_day_work = "+" in parts or attendance_status in (
		"Present",
		"Half Day",
		"Work From Home",
		"Work Trip",
	)
	if day_type == "holiday":
		# L is actual work on a public holiday; NL is paid holiday leave.
		return ("L", "holiday", 1.0) if has_off_day_work else (
			"NL",
			"public_holiday",
			1.0,
		)
	if day_type == "off":
		# The handed-over legend defines CN as *working* on Sunday, not a
		# regular Sunday rest day. A single punch (+1) is not a work pair.
		return (
			("CN", "sunday", 1.0)
			if work_date.weekday() == 6 and has_off_day_work
			else ("", "off", 0.0)
		)

	if "V" in parts or "KV" in parts or "KR" in parts:
		return shift_symbol, "anomaly", 0.0
	if technical_symbol == "CT":
		return "CT", "work", 1.0
	if technical_symbol in ("P", "H", "Ro"):
		return {
			"P": ("P", "paid_leave", 1.0),
			"H": ("P", "paid_leave", 0.5),
			"Ro": ("R0", "unpaid_reason", 1.0),
		}[technical_symbol]
	if 0 < working_hours < 8:
		return str(max(1, min(7, int(math.floor(working_hours))))), "short_work", 1.0
	return shift_symbol, "night" if shift_symbol == "Đ" else "work", 1.0


def _leave_symbol(leave_type):
	normalized = _normalize(leave_type)
	if any(keyword in normalized for keyword in ("om", "benh", "thai san", "bhxh")):
		return "Ô", "sick", 1.0
	if any(keyword in normalized for keyword in ("nghi mat", "du lich")):
		return "NM", "special_leave", 1.0
	if any(keyword in normalized for keyword in ("cuoi", "ket hon")):
		return "CH", "family_leave", 1.0
	if any(keyword in normalized for keyword in ("tang", "ma chay")):
		return "TL", "family_leave", 1.0
	if "nghi bu" in normalized:
		return "NB", "comp_leave", 1.0
	if any(keyword in normalized for keyword in ("cong tac", "di hoc", "di hop")):
		return "CT", "work", 1.0
	if "khong luong" in normalized:
		if any(keyword in normalized for keyword in ("khong ly do", "tu y", "vang")):
			return "L0", "unpaid_no_reason", 1.0
		return "R0", "unpaid_reason", 1.0
	return "P", "paid_leave", 1.0


def _anomaly_state(symbol, day_type):
	parts = set((symbol or "").split("/"))
	if "KV" in parts:
		return "missing_in"
	if "KR" in parts:
		return "missing_out"
	if day_type == "work" and "V" in parts:
		return "absent"
	return ""


def _apply_attendance_totals(row, day):
	units = float(day.units or 0)
	category = day.category
	if category == "work":
		row.tot_work_days += units
	elif category == "night":
		row.tot_night += units
	elif category == "short_work":
		row.tot_work_hours += float(day.working_hours or 0)
	elif category == "sick":
		row.tot_sick += units
	elif category == "sunday":
		row.tot_sunday += units
	elif category == "holiday":
		row.tot_holiday += units
	elif category == "public_holiday":
		row.tot_public_holiday += units
	elif category == "special_leave":
		row.tot_special_leave += units
	elif category == "paid_leave":
		row.tot_paid_leave += units
	elif category == "family_leave":
		row.tot_family_leave += units
	elif category == "comp_leave":
		row.tot_comp_leave += units
	elif category == "unpaid_reason":
		row.tot_unpaid_reason += units
	elif category == "unpaid_no_reason":
		row.tot_unpaid_no_reason += units


def _apply_overtime_totals(row, day):
	hours = float(day.overtime_hours or 0)
	if day.day_category == "holiday":
		row.tot_overtime_holiday += hours
	elif day.day_category == "off":
		row.tot_overtime_off += hours
	else:
		row.tot_overtime_normal += hours


def _calculate_overtime_hours(*, employee, day_type, window, planned_logs, outside_logs):
	logs = _unique_sorted_logs([*(planned_logs or []), *(outside_logs or [])])
	if len(logs) < 2:
		return 0.0
	if (not window or window.get("is_off")) and not (
		employee.get("custom_shift_group") or employee.get("default_shift")
	):
		# Without a work plan there is no supported baseline that separates
		# normal work from overtime.  Do not turn all observed time into OT.
		return 0.0
	first = get_datetime(logs[0].time)
	last = get_datetime(logs[-1].time)
	if last <= first:
		return 0.0

	if day_type in ("off", "holiday") or not window or window.get("is_off"):
		hours = (last - first).total_seconds() / 3600
	else:
		# Early punches are frequently the OUT of the preceding night shift.
		# The supplied overtime sheet records completed time after the planned
		# shift, so only the tail beyond today's planned end is counted here.
		after = max(0.0, (last - window.end_datetime).total_seconds() / 3600)
		hours = after
	# The handed-over workbook records whole hours rounded from the first/last
	# biometric interval (for example 5h40 -> 6 and 7h59 -> 8).
	return float(max(0, min(24, math.floor(hours + 0.5))))


def _shift_symbol(window):
	if not window or window.get("is_off") or not window.get("shift_type"):
		return "X"
	name = _normalize(window.shift_type)
	if "sang" in name:
		return "S"
	if "chieu" in name:
		return "C"
	if "dem" in name or window.get("is_overnight"):
		return "Đ"
	return "X"


def _holiday_description(employee, window, holiday_context, work_date):
	holiday_list = None
	if window and window.get("shift_doc"):
		holiday_list = window.shift_doc.holiday_list
	holiday_list = holiday_list or employee.get("holiday_list") or holiday_context.company_lists.get(
		employee.company
	)
	holiday = holiday_context.holidays.get(holiday_list, {}).get(work_date)
	return holiday.description if holiday else ""


def _enrich_employees(employees):
	if not employees:
		return
	fields = [
		"name",
		"employee_number",
		"attendance_device_id",
		"designation",
		"custom_designation_group",
		"custom_working_schedule_type",
		"custom_shift_group",
	]
	if frappe.get_meta("Employee").has_field("custom_employee_code"):
		fields.append("custom_employee_code")
	rows = frappe.get_all(
		"Employee",
		filters={"name": ["in", [employee.name for employee in employees]]},
		fields=fields,
	)
	by_name = {row.name: row for row in rows}
	for employee in employees:
		for fieldname, value in (by_name.get(employee.name) or {}).items():
			employee[fieldname] = value

	department_names = list({employee.department for employee in employees if employee.department})
	if not department_names:
		return
	department_fields = ["name"]
	department_meta = frappe.get_meta("Department")
	for fieldname in ("custom_short_name", "custom_short_text_qlvb"):
		if department_meta.has_field(fieldname):
			department_fields.append(fieldname)
	departments = {
		row.name: row
		for row in frappe.get_all(
			"Department",
			filters={"name": ["in", department_names]},
			fields=department_fields,
		)
	}
	for employee in employees:
		department = departments.get(employee.department) or {}
		employee.department_code = (
			department.get("custom_short_name")
			or department.get("custom_short_text_qlvb")
			or _department_code(employee.department)
		)


def _employee_section(employee):
	if employee.get("custom_working_schedule_type") == "Theo kíp":
		return (
			"II. BỘ PHẬN SẢN XUẤT",
			employee.get("custom_designation_group")
			or _short_department(employee.department)
			or "Chưa phân nhóm",
		)
	return "I. BỘ PHẬN PHỤC VỤ SẢN XUẤT", ""


def _employee_shift_label(employee):
	return (
		employee.get("custom_shift_group")
		or employee.get("default_shift")
		or employee.get("custom_working_schedule_type")
		or ""
	)


def _department_code(department):
	name = _short_department(department)
	words = [part for part in name.replace("-", " ").split() if part]
	ignored = {"phòng", "ban", "bộ", "phận", "tổ", "công", "đoạn"}
	initials = "".join(word[0] for word in words if word.lower() not in ignored)
	return strip_accents(initials).upper()[:5] or strip_accents(name)[:5].upper()


def _short_department(department):
	if not department:
		return ""
	return department.rsplit(" - ", 1)[0].strip()


def _unique_sorted_logs(logs):
	unique = {row.name: row for row in logs}
	return sorted(unique.values(), key=lambda row: get_datetime(row.time))


def _empty_day(category):
	return frappe._dict(
		symbol="",
		state="",
		label="",
		confirmation_name=None,
		review_state="",
		review_label="",
		technical_symbol="",
		category=category,
		units=0.0,
		working_hours=0.0,
		overtime_hours=0.0,
		day_category="normal",
	)


def _contains(value, keywords):
	normalized = _normalize(value)
	return any(_normalize(keyword) in normalized for keyword in keywords)


def _normalize(value):
	return strip_accents(value or "").strip().lower()


def _date_range(from_date, to_date):
	current = getdate(from_date)
	while current <= getdate(to_date):
		yield current
		current += timedelta(days=1)


def _days_in_month(year, month):
	if month == 12:
		return 31
	return ((date(year, month + 1, 1) - timedelta(days=1))).day

