"""Shift-aware monthly attendance matrix and symbol definitions."""

from __future__ import annotations

from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, escape_html, getdate, today

from vinatex.vnt_hr.attendance_processing import (
	build_shift_windows,
	calculate_attendance_details,
	classify_work_date,
	load_checkins_for_windows,
	load_holiday_context,
)
from vinatex.vnt_hr.report.tổng_hợp_chấm_công_tháng.tổng_hợp_chấm_công_tháng import (
	_categorize_leave,
	_leave_type_group_map,
)
from vinatex.vnt_hr.shift_management.work_schedule_filter import (
	WORK_SCHEDULE_FILTERS,
	matches_work_schedule_filter,
)


SYMBOLS = {
	"late": "Tr",
	"early": "Sm",
	"on_time": "X",
	"overtime": "+",
	"single_outside": "+1",
	"missing_out": "KR",
	"missing_in": "KV",
	"absent": "V",
	"overnight": "Đ",
	"off": "Off",
	"holiday": "L",
	"leave": "P",
	"half_day": "H",
	"business_trip": "CT",
	"not_joined": "CV",
	"unpaid_leave": "Ro",
}


def execute(filters):
	filters = frappe._dict(filters or {})
	from_date, to_date = _validate_filters(filters)
	days = list(_date_range(from_date, to_date))
	columns = get_columns(days)
	employees = _get_employees(filters, from_date, to_date)
	if not employees:
		return columns, [], get_legend()

	effective_end_date = min(to_date, getdate(add_days(today(), -1)))
	windows = build_shift_windows(employees, from_date, to_date)
	checkins, unplanned = load_checkins_for_windows(employees, windows, from_date, to_date)
	holiday_context = load_holiday_context(employees, windows, from_date, to_date)
	attendance_map = _get_attendance_map(employees, from_date, to_date)
	leave_map = _get_leave_map(employees, from_date, to_date)
	leave_groups = _leave_type_group_map()
	confirmation_map = _get_confirmation_map(employees, from_date, to_date)
	can_open_confirmation = bool(
		{"HR User", "HR Manager", "System Manager"}.intersection(frappe.get_roles())
	)

	data = []
	for employee in employees:
		row = _new_row(employee)
		resolved_groups = []
		for work_date in days:
			group = windows.get((employee.name, work_date), {}).get("shift_group")
			if group and group not in resolved_groups:
				resolved_groups.append(group)
		if resolved_groups:
			row["shift_group"] = " → ".join(resolved_groups)
		joining_date = getdate(employee.date_of_joining) if employee.date_of_joining else date.min
		for work_date in days:
			fieldname = f"d{work_date.day:02d}"
			if work_date > effective_end_date:
				row[fieldname] = ""
				continue
			if work_date < joining_date:
				row[fieldname] = SYMBOLS["not_joined"]
				row["tot_not_joined"] += 1
				continue

			key = (employee.name, work_date)
			window = windows.get(key)
			logs = checkins.get(key, [])
			unplanned_logs = unplanned.get(key, [])
			attendance = attendance_map.get(key)
			leave = leave_map.get(key)
			confirmation = confirmation_map.get(key)
			day_type = classify_work_date(employee, window, holiday_context)
			symbol = _get_symbol(
				employee,
				window,
				logs,
				unplanned_logs,
				attendance,
				leave,
				leave_groups,
				day_type,
			)
			row[fieldname] = symbol
			if _confirmation_applies(symbol, day_type, confirmation):
				review = _build_confirmation_review(
					confirmation,
					include_document_name=can_open_confirmation,
				)
				row[fieldname] = _symbol_after_confirmation(symbol, window, review)
				row[f"{fieldname}__hr_review"] = review
				_apply_totals(row, symbol, review)
			else:
				_apply_totals(row, symbol)
		if _matches_confirmation_filter(row, filters.get("confirmation_status")):
			data.append(row)

	return columns, data, get_legend()


def get_columns(days):
	columns = [
		# {"fieldname": "employee", "label": _("Mã NV"), "fieldtype": "Link", "options": "Employee", "width": 105},
		{"fieldname": "employee_name", "label": _("Tên nhân viên"), "fieldtype": "Data", "width": 170},
		{"fieldname": "department", "label": _("Phòng ban"), "fieldtype": "Data", "width": 150},
		{"fieldname": "shift_group", "label": _("Kíp"), "fieldtype": "Data", "width": 75},
	]
	for day in days:
		columns.append(
			{
				"fieldname": f"d{day.day:02d}",
				"label": f"{day.day:02d}",
				"fieldtype": "Data",
				"width": 58,
				"align": "center",
			}
		)
	columns.extend(
		[
			{"fieldname": "tot_present", "label": _("Có mặt"), "fieldtype": "Float", "width": 75},
			{"fieldname": "tot_late", "label": _("Đi trễ"), "fieldtype": "Int", "width": 70},
			{"fieldname": "tot_early", "label": _("Về sớm"), "fieldtype": "Int", "width": 75},
			{"fieldname": "tot_missing_in", "label": _("Thiếu vào"), "fieldtype": "Int", "width": 78},
			{"fieldname": "tot_missing_out", "label": _("Thiếu ra"), "fieldtype": "Int", "width": 75},
			{"fieldname": "tot_absent", "label": _("Vắng"), "fieldtype": "Float", "width": 65},
			{"fieldname": "tot_overtime", "label": _("Có log ngoài ca"), "fieldtype": "Int", "width": 105},
			{"fieldname": "tot_off", "label": _("Off"), "fieldtype": "Int", "width": 60},
			{"fieldname": "tot_pending_confirmation", "label": _("Chờ HR"), "fieldtype": "Int", "width": 72},
			{"fieldname": "tot_approved_confirmation", "label": _("HR đồng ý"), "fieldtype": "Int", "width": 82},
			{"fieldname": "tot_rejected_confirmation", "label": _("HR từ chối"), "fieldtype": "Int", "width": 82},
			{"fieldname": "tot_incomplete_approved_time", "label": _("ĐY thiếu giờ"), "fieldtype": "Int", "width": 92},
			{"fieldname": "tot_leave", "label": _("Nghỉ phép"), "fieldtype": "Float", "width": 85},
			{"fieldname": "tot_business_trip", "label": _("Công tác"), "fieldtype": "Float", "width": 75},
			{"fieldname": "tot_holiday", "label": _("Nghỉ lễ"), "fieldtype": "Float", "width": 75},
		]
	)
	return columns


def get_legend():
	groups = [
		(
			"work",
			_("Công làm việc"),
			[
				("X", _("Đúng giờ, ca không qua đêm")),
				("Đ", _("Đúng giờ, ca có qua đêm")),
				("Tr", _("Đi trễ")),
				("Sm", _("Về sớm")),
				("Tr/Sm", _("Vừa đi trễ vừa về sớm")),
				("CT", _("Công tác")),
			],
		),
		(
			"leave",
			_("Nghỉ phép / không lương"),
			[
				("P", _("Nghỉ phép")),
				("H", _("Nghỉ nửa ngày")),
				("Ro", _("Nghỉ không lương")),
			],
		),
		(
			"rest",
			_("Chấm công bất thường"),
			[
				("KR", _("Thiếu giờ ra")),
				("KV", _("Thiếu giờ vào")),
				(
					"+",
					_("Có từ hai lần chấm ngoài ca/ngày OFF; HR cần xác nhận tăng ca"),
				),
				(
					"+1",
					_("Chỉ có một lần chấm ngoài ca; chưa đủ cặp vào/ra"),
				),
				("V", _("Vắng, không có log hợp lệ trong ca kế hoạch")),
				(
					"V/+ hoặc V/+1",
					_("Không có log hợp lệ trong ca nhưng có chấm ngoài ca"),
				),
				(
					"KV/KR + /+ hoặc /+1",
					_("Thiếu giờ hợp lệ trong ca và đồng thời có chấm ngoài ca"),
				),
			],
		),
		(
			"other",
			_("Ngày nghỉ / khác"),
			[
				("Off", _("Ngày không xếp ca")),
				("L", _("Nghỉ lễ")),
				("CV", _("Chưa vào làm")),
			],
		),
		(
			"review",
			_("Kết quả giải trình của HR"),
			[
				("?", _("Chưa có quyết định của HR")),
				(
					"ĐY",
					_("HR đồng ý; riêng Sm được miễn về sớm và chuyển thành X"),
				),
				("ĐY*", _("HR đồng ý nhưng +1 chưa đủ để tính thời lượng ngoài ca")),
				(
					"TC",
					_("HR từ chối; Sm vẫn giữ nguyên, các trường hợp khác theo quy tắc hiện hành"),
				),
			],
		),
	]

	group_html = []
	for style, title, items in groups:
		items_html = "".join(
			f"<div class='vnt-attendance-legend__item'>"
			f"<span class='vnt-attendance-legend__code'>{escape_html(code)}</span>"
			f"<span class='vnt-attendance-legend__description'>{escape_html(label)}</span>"
			f"</div>"
			for code, label in items
		)
		group_html.append(
			f"<section class='vnt-attendance-legend__group is-{style}'>"
			f"<h4 class='vnt-attendance-legend__group-title'>"
			f"<span class='vnt-attendance-legend__dot'></span>{escape_html(title)}"
			f"</h4>{items_html}</section>"
		)

	return (
		"<details class='vnt-attendance-legend' open>"
		"<summary class='vnt-attendance-legend__summary'>"
		f"<span>{escape_html(_('Chú thích ký hiệu chấm công'))}</span>"
		"</summary>"
		f"<div class='vnt-attendance-legend__grid'>{''.join(group_html)}</div>"
		"<div class='vnt-attendance-legend__note'>"
		f"{escape_html(_('Các ký hiệu Tr và Sm được tính trực tiếp từ giờ ca và thời gian ân hạn của Shift Type; không phụ thuộc Enable Auto Attendance.'))}"
		"<br>"
		f"{escape_html(_('Phần đứng trước dấu / là kết quả theo ca kế hoạch; + hoặc +1 phía sau là bằng chứng chấm ngoài ca cần HR kiểm tra trong Giải trình chấm công.'))}"
		"<br>"
		f"{escape_html(_('Bấm vào ô có huy hiệu HR để mở phiếu giải trình. Đồng ý với +1 chỉ xác nhận có làm, không tự tạo giờ vào/ra hoặc số giờ tăng ca.'))}"
		"<br>"
		f"{escape_html(_('Với Sm: HR Đồng ý sẽ chuyển thành X; Từ chối giữ Sm. Nếu là Tr/Sm thì Đồng ý chỉ bỏ Sm và vẫn giữ Tr.'))}"
		"</div></details>"
	)


def _get_symbol(
	employee,
	window,
	logs,
	unplanned_logs,
	attendance,
	leave,
	leave_groups,
	day_type,
):
	attendance_status = (attendance.status or "").strip() if attendance else ""
	outside_symbol = _outside_evidence_symbol(unplanned_logs)
	off_day_evidence = _outside_evidence_symbol([*(logs or []), *(unplanned_logs or [])])
	has_work = bool(logs or unplanned_logs) or attendance_status in (
		"Present",
		"Half Day",
		"Work From Home",
		"Work Trip",
	)

	if day_type == "holiday":
		if off_day_evidence:
			return off_day_evidence
		return SYMBOLS["overtime"] if has_work else SYMBOLS["holiday"]
	if day_type == "off":
		if off_day_evidence:
			return off_day_evidence
		return SYMBOLS["overtime"] if has_work else SYMBOLS["off"]

	if attendance_status == "On Leave":
		return _leave_symbol(attendance.leave_type, leave_groups, half_day=False)
	if attendance_status == "Half Day" and attendance.leave_type:
		return SYMBOLS["half_day"]
	if attendance_status == "Work Trip":
		return SYMBOLS["business_trip"]

	if leave:
		if cint(leave.half_day) and getdate(leave.half_day_date) == window.work_date:
			return SYMBOLS["half_day"]
		return _leave_symbol(leave.leave_type, leave_groups, half_day=False)

	if cint(employee.custom_need_check):
		return SYMBOLS["overnight"] if window.is_overnight else SYMBOLS["on_time"]

	if not logs:
		if attendance_status == "Half Day":
			return _combine_with_outside(SYMBOLS["half_day"], outside_symbol)
		if attendance_status in ("Present", "Work From Home"):
			base_symbol = SYMBOLS["overnight"] if window.is_overnight else SYMBOLS["on_time"]
			return _combine_with_outside(base_symbol, outside_symbol)
		return _combine_with_outside(SYMBOLS["absent"], outside_symbol)

	# The monthly matrix is an independent reconciliation report. It must show
	# schedule deviations even when HRMS Auto Attendance and its marking switches
	# are disabled. Attendance creation keeps the standard flag-controlled mode.
	details = calculate_attendance_details(
		window, logs, respect_marking_flags=False
	)
	if not details.has_in and not details.has_out:
		return _combine_with_outside(SYMBOLS["absent"], outside_symbol)
	if not details.has_in:
		return _combine_with_outside(SYMBOLS["missing_in"], outside_symbol)
	if not details.has_out:
		return _combine_with_outside(SYMBOLS["missing_out"], outside_symbol)
	if attendance_status == "Absent" or details.status == "Absent":
		return SYMBOLS["absent"]
	if attendance_status == "Half Day" or details.status == "Half Day":
		return SYMBOLS["half_day"]

	# Use the punches and today's resolved plan as the report source of truth.
	# Persisted Attendance flags may have been calculated under older settings
	# and must not create stale Tr/Sm results after a shift-plan change.
	late = details.late_entry
	early = details.early_exit
	if late and early:
		base_symbol = f"{SYMBOLS['late']}/{SYMBOLS['early']}"
	elif late:
		base_symbol = SYMBOLS["late"]
	elif early:
		base_symbol = SYMBOLS["early"]
	else:
		base_symbol = SYMBOLS["overnight"] if window.is_overnight else SYMBOLS["on_time"]
	return _combine_with_outside(base_symbol, outside_symbol)


def _outside_evidence_symbol(unplanned_logs):
	"""Return an evidence marker without guessing a missing IN/OUT direction.

	One outside punch cannot form a work interval, so it is shown as ``+1``.
	Two or more punches provide a first/last pair and retain the existing ``+``.
	The actual overtime decision remains with HR in VNT Attendance Confirm.
	"""
	count = len(unplanned_logs or [])
	if count == 1:
		return SYMBOLS["single_outside"]
	if count >= 2:
		return SYMBOLS["overtime"]
	return ""


def _combine_with_outside(base_symbol, outside_symbol):
	if not outside_symbol:
		return base_symbol
	if base_symbol in (SYMBOLS["overtime"], SYMBOLS["single_outside"]):
		return base_symbol
	return f"{base_symbol}/{outside_symbol}"


def _confirmation_applies(symbol, day_type, confirmation):
	"""Only apply a decision while its technical anomaly still exists."""
	if not confirmation:
		return False
	parts = set((symbol or "").split("/"))
	issue_code = confirmation.get("issue_code")
	if issue_code == "OFF_WITH_CHECKIN":
		return day_type == "off" and bool(parts & {"+", "+1"})
	if issue_code == "WORKDAY_OUTSIDE_ONLY":
		return "V" in parts and bool(parts & {"+", "+1"})
	if issue_code in ("WORKDAY_NO_CHECKIN", "WORKDAY_INVALID_CHECKINS"):
		return day_type == "work" and parts == {"V"}
	if issue_code == "MISSING_IN":
		return "KV" in parts
	if issue_code == "MISSING_OUT":
		return "KR" in parts
	if issue_code == "EARLY_EXIT":
		return day_type == "work" and "Sm" in parts
	if issue_code == "WORKDAY_OVERTIME":
		return day_type == "work" and bool(parts & {"+", "+1"})
	return False


def _build_confirmation_review(confirmation, *, include_document_name=False):
	decision = (confirmation.get("confirm") or "").strip()
	evidence_code = (confirmation.get("evidence_code") or "").strip()
	if decision == "Đồng ý":
		state = "approved_incomplete" if evidence_code == "+1" else "approved"
	elif decision == "Từ chối":
		state = "rejected"
	else:
		state = "pending"
	labels = {
		"pending": "Chờ HR",
		"approved": "HR đồng ý",
		"approved_incomplete": "HR đồng ý - chưa đủ thời gian",
		"rejected": "HR từ chối",
	}
	issue_code = confirmation.get("issue_code")
	if issue_code == "EARLY_EXIT":
		labels.update(
			{
				"pending": "Chờ HR xác nhận về sớm",
				"approved": "HR đồng ý: chuyển Sm thành X",
				"rejected": "HR từ chối: giữ Sm",
			}
		)
	return frappe._dict(
		state=state,
		label=labels[state],
		issue_code=issue_code,
		evidence_code=evidence_code,
		document_name=confirmation.get("parent") if include_document_name else None,
	)


def _symbol_after_confirmation(symbol, window, review):
	"""Return the visible final symbol without changing source records.

	An approved EARLY_EXIT waives only ``Sm``.  Any independent ``Tr`` remains,
	and a pure Sm becomes the normal full-work symbol for that planned shift.
	"""
	if not review or review.get("issue_code") != "EARLY_EXIT":
		return symbol
	if review.get("state") not in ("approved", "approved_incomplete"):
		return symbol

	remaining = [part for part in (symbol or "").split("/") if part and part != "Sm"]
	if remaining:
		return "/".join(remaining)
	return SYMBOLS["overnight"] if window and window.get("is_overnight") else SYMBOLS["on_time"]


def _matches_confirmation_filter(row, selected_status):
	if not selected_status:
		return True
	counts = {
		"Có bất thường": (
			row["tot_pending_confirmation"]
			+ row["tot_approved_confirmation"]
			+ row["tot_rejected_confirmation"]
		),
		"Chờ HR": row["tot_pending_confirmation"],
		"HR đồng ý": row["tot_approved_confirmation"],
		"HR từ chối": row["tot_rejected_confirmation"],
		"Đồng ý nhưng thiếu thời gian": row["tot_incomplete_approved_time"],
	}
	return bool(counts.get(selected_status, 0))


def _leave_symbol(leave_type, leave_groups, *, half_day=False):
	if half_day:
		return SYMBOLS["half_day"]
	category = _categorize_leave(leave_type, leave_groups.get(leave_type))
	if category == "business_trip":
		return SYMBOLS["business_trip"]
	if category == "unpaid":
		return SYMBOLS["unpaid_leave"]
	return SYMBOLS["leave"]


def _apply_totals(row, symbol, review=None):
	if not symbol:
		return
	parts = set(symbol.split("/"))

	# Technical anomaly counters always reflect Checkin/shift evidence. Final
	# Present/Absent/Off totals are held until HR makes the one-level decision.
	if review:
		state = review.get("state")
		if review.get("issue_code") == "WORKDAY_OVERTIME":
			# The planned IN/OUT pair establishes the normal workday.  HR only
			# decides whether the additional outside punches count as overtime.
			row["tot_present"] += 1
			if "Tr" in parts:
				row["tot_late"] += 1
			if "Sm" in parts:
				row["tot_early"] += 1
			if parts & {"+", "+1"}:
				row["tot_overtime"] += 1
			if state == "pending":
				row["tot_pending_confirmation"] += 1
			elif state in ("approved", "approved_incomplete"):
				row["tot_approved_confirmation"] += 1
				if state == "approved_incomplete":
					row["tot_incomplete_approved_time"] += 1
			elif state == "rejected":
				row["tot_rejected_confirmation"] += 1
			return
		if review.get("issue_code") == "EARLY_EXIT":
			# A complete punch pair is present work regardless of the decision.
			# Approval waives only the early-exit violation; rejection keeps Sm.
			row["tot_present"] += 1
			if "Tr" in parts:
				row["tot_late"] += 1
			if "Sm" in parts and state not in ("approved", "approved_incomplete"):
				row["tot_early"] += 1
			if state == "pending":
				row["tot_pending_confirmation"] += 1
			elif state in ("approved", "approved_incomplete"):
				row["tot_approved_confirmation"] += 1
			elif state == "rejected":
				row["tot_rejected_confirmation"] += 1
			return

		if "Tr" in parts:
			row["tot_late"] += 1
		if "Sm" in parts:
			row["tot_early"] += 1
		if "KV" in parts:
			row["tot_missing_in"] += 1
		if "KR" in parts:
			row["tot_missing_out"] += 1
		if parts & {"+", "+1"}:
			row["tot_overtime"] += 1

		if state == "pending":
			row["tot_pending_confirmation"] += 1
			return
		if state in ("approved", "approved_incomplete"):
			row["tot_approved_confirmation"] += 1
			if state == "approved_incomplete":
				row["tot_incomplete_approved_time"] += 1
			if review.get("issue_code") != "OFF_WITH_CHECKIN":
				row["tot_present"] += 1
			return
		if state == "rejected":
			row["tot_rejected_confirmation"] += 1
			if review.get("issue_code") == "OFF_WITH_CHECKIN":
				row["tot_off"] += 1
			else:
				row["tot_absent"] += 1
			return

	if parts & {"X", "Đ", "Tr", "Sm", "KR", "KV"}:
		row["tot_present"] += 1
	if "Tr" in parts:
		row["tot_late"] += 1
	if "Sm" in parts:
		row["tot_early"] += 1
	if "KV" in parts:
		row["tot_missing_in"] += 1
	if "KR" in parts:
		row["tot_missing_out"] += 1
	if parts & {"V", "Ro"}:
		row["tot_absent"] += 1
	if parts & {"+", "+1"}:
		row["tot_overtime"] += 1
	if symbol == "Off":
		row["tot_off"] += 1
	if symbol == "P":
		row["tot_leave"] += 1
	if symbol == "CT":
		row["tot_business_trip"] += 1
	if symbol == "H":
		row["tot_present"] += 0.5
		row["tot_leave"] += 0.5
	if symbol == "L":
		row["tot_holiday"] += 1


def _new_row(employee):
	return {
		"employee": employee.name,
		"employee_name": employee.employee_name,
		"department": employee.get("department_display") or employee.department,
		"shift_group": employee.get("custom_shift_group")
		or (employee.default_shift if (employee.default_shift or "").startswith("Kíp ") else None),
		"tot_present": 0.0,
		"tot_late": 0,
		"tot_early": 0,
		"tot_missing_in": 0,
		"tot_missing_out": 0,
		"tot_absent": 0.0,
		"tot_overtime": 0,
		"tot_off": 0,
		"tot_pending_confirmation": 0,
		"tot_approved_confirmation": 0,
		"tot_rejected_confirmation": 0,
		"tot_incomplete_approved_time": 0,
		"tot_leave": 0.0,
		"tot_business_trip": 0.0,
		"tot_holiday": 0.0,
		"tot_not_joined": 0,
	}


def _get_employees(filters, from_date, to_date):
	db_filters = {"status": "Active", "company": filters.company}
	for fieldname in ("department", "branch"):
		if filters.get(fieldname):
			db_filters[fieldname] = filters.get(fieldname)
	if filters.get("employee"):
		db_filters["name"] = filters.employee

	# Non-HR users can only open their own row even if a crafted request omits
	# the Employee filter.
	privileged_roles = {"HR User", "HR Manager", "System Manager"}
	if not privileged_roles.intersection(frappe.get_roles()):
		own_employee = frappe.db.get_value(
			"Employee", {"user_id": frappe.session.user, "status": "Active"}, "name"
		)
		if not own_employee:
			return []
		db_filters["name"] = own_employee

	fields = [
		"name",
		"employee_name",
		"company",
		"department",
		"designation",
		"branch",
		"date_of_joining",
		"relieving_date",
		"holiday_list",
		"default_shift",
		"custom_need_check",
	]
	if frappe.get_meta("Employee").has_field("custom_shift_group"):
		fields.append("custom_shift_group")
	if frappe.get_meta("Employee").has_field("custom_working_schedule_type"):
		fields.append("custom_working_schedule_type")
	rows = frappe.get_list("Employee", filters=db_filters, fields=fields, order_by="department, employee_name")
	rows = [
		row
		for row in rows
		if matches_work_schedule_filter(row, filters.get("work_schedule_filter"))
	]
	department_ids = list({row.department for row in rows if row.department})
	department_names = {}
	if department_ids:
		department_names = {
			row.name: row.department_name
			for row in frappe.get_all(
				"Department",
				filters={"name": ["in", department_ids]},
				fields=["name", "department_name"],
			)
		}
	for row in rows:
		# Employee.department là tên document, thường có dạng
		# "Tên phòng ban - viết tắt công ty". Chỉ department_name
		# được đưa ra báo cáo; Link gốc vẫn được giữ để lọc/xử lý.
		row.department_display = department_names.get(row.department) or row.department
	return [
		row
		for row in rows
		if (not row.date_of_joining or getdate(row.date_of_joining) <= to_date)
		and (not row.relieving_date or getdate(row.relieving_date) >= from_date)
	]


def _get_attendance_map(employees, from_date, to_date):
	rows = frappe.get_all(
		"Attendance",
		filters={
			"employee": ["in", [row.name for row in employees]],
			"attendance_date": ["between", [from_date, to_date]],
			"docstatus": ["<", 2],
		},
		fields=[
			"name",
			"employee",
			"attendance_date",
			"status",
			"leave_type",
			"shift",
			"in_time",
			"out_time",
			"late_entry",
			"early_exit",
			"docstatus",
		],
		order_by="docstatus desc, modified desc",
	)
	result = {}
	for row in rows:
		result.setdefault((row.employee, getdate(row.attendance_date)), row)
	return result


def _get_confirmation_map(employees, from_date, to_date):
	employee_names = tuple(row.name for row in employees)
	if not employee_names:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT
			p.name AS parent,
			p.employee,
			i.date,
			i.issue_code,
			i.evidence_code,
			i.confirm,
			i.reviewed_on,
			p.modified
		FROM `tabVNT Attendance Confirm Item` i
		INNER JOIN `tabVNT Attendance Confirm` p ON p.name = i.parent
		WHERE p.docstatus < 2
		  AND p.employee IN %(employees)s
		  AND i.date BETWEEN %(from_date)s AND %(to_date)s
		ORDER BY p.modified DESC, i.idx DESC
		""",
		{
			"employees": employee_names,
			"from_date": from_date,
			"to_date": to_date,
		},
		as_dict=True,
	)
	result = {}
	for row in rows:
		result.setdefault((row.employee, getdate(row.date)), row)
	return result


def _get_leave_map(employees, from_date, to_date):
	rows = frappe.get_all(
		"Leave Application",
		filters={
			"employee": ["in", [row.name for row in employees]],
			"docstatus": 1,
			"status": "Approved",
			"from_date": ["<=", to_date],
			"to_date": [">=", from_date],
		},
		fields=["employee", "from_date", "to_date", "half_day", "half_day_date", "leave_type"],
	)
	result = {}
	for row in rows:
		for leave_date in _date_range(
			max(getdate(row.from_date), from_date), min(getdate(row.to_date), to_date)
		):
			result.setdefault((row.employee, leave_date), row)
	return result


def _validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Company is required."))
	if filters.get("work_schedule_filter") not in (None, "", *WORK_SCHEDULE_FILTERS):
		frappe.throw(_("Invalid work schedule filter."))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are required."))
	from_date, to_date = getdate(filters.from_date), getdate(filters.to_date)
	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date."))
	if (to_date - from_date).days > 366:
		frappe.throw(_("Report range cannot exceed 366 days."))
	return from_date, to_date


def _date_range(from_date, to_date):
	current = getdate(from_date)
	while current <= getdate(to_date):
		yield current
		current += timedelta(days=1)
