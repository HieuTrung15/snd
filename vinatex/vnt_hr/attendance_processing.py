"""Shared shift-aware attendance processing for factory and office employees.

The standard HRMS auto-attendance pipeline expects Employee Checkin.shift and
shift_start to be correct at insert time. Biometric logs in this installation
can arrive before a Shift Assignment is generated, so this module resolves the
plan again by work date and groups logs by the configured shift window. This is
also the single source used by attendance reports, including overnight shifts.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, get_time, getdate, now_datetime
from hrms.hr.doctype.employee_checkin.employee_checkin import (
	calculate_working_hours,
	update_attendance_in_checkins,
)

from vinatex.vnt_hr.shift_management.constants import MAX_MANUAL_GENERATION_DAYS
from vinatex.vnt_hr.shift_management.shift_assignment_service import (
	_date_range,
	_load_generation_context,
	_plan_employee_date,
	generate_shift_assignments,
)


def get_active_employees(from_date, to_date, employee_names=None):
	"""Return active employees whose employment period overlaps the range."""
	from_date, to_date = getdate(from_date), getdate(to_date)
	filters = {"status": "Active"}
	if employee_names:
		filters["name"] = ["in", list(employee_names)]

	fields = [
		"name",
		"employee_name",
		"company",
		"department",
		"branch",
		"designation",
		"date_of_joining",
		"relieving_date",
		"holiday_list",
		"default_shift",
		"custom_need_check",
	]
	if frappe.get_meta("Employee").has_field("custom_shift_group"):
		fields.append("custom_shift_group")

	rows = frappe.get_all("Employee", filters=filters, fields=fields, order_by="name")
	return [
		row
		for row in rows
		if (not row.date_of_joining or getdate(row.date_of_joining) <= to_date)
		and (not row.relieving_date or getdate(row.relieving_date) >= from_date)
	]


def build_shift_windows(employees, from_date, to_date, context=None):
	"""Resolve one planned work window per employee/work date.

	Precedence is inherited from the shift generator: an existing Shift
	Assignment wins, followed by effective Kíp membership/schedule. Employees
	outside the Kíp model continue to use Employee.default_shift.
	"""
	from_date, to_date = getdate(from_date), getdate(to_date)
	employees = [frappe._dict(employee) for employee in employees]
	context = context or _load_generation_context(employees, from_date, to_date)
	shift_names = set(context.get("shift_types") or [])
	shift_docs = {
		name: frappe.get_cached_doc("Shift Type", name)
		for name in shift_names
	}
	windows = {}

	for employee in employees:
		for work_date in _date_range(from_date, to_date):
			if (
				(employee.date_of_joining and work_date < getdate(employee.date_of_joining))
				or (employee.relieving_date and work_date > getdate(employee.relieving_date))
			):
				windows[(employee.name, work_date)] = frappe._dict(
					employee=employee.name,
					work_date=work_date,
					shift_group=None,
					shift_type=None,
					assignment_source="Employment period",
					plan_action="OUTSIDE_EMPLOYMENT",
					plan_error=None,
					is_off=True,
				)
				continue
			plan = frappe._dict(_plan_employee_date(employee, work_date, context))
			if plan.action == "SKIP_NO_GROUP" and employee.default_shift:
				plan.shift_type = employee.default_shift
				plan.assignment_source = "Employee.default_shift"
			if plan.shift_type and plan.shift_type not in shift_docs:
				shift_docs[plan.shift_type] = frappe.get_cached_doc("Shift Type", plan.shift_type)

			window = frappe._dict(
				employee=employee.name,
				work_date=work_date,
				shift_group=plan.shift_group,
				shift_type=plan.shift_type,
				assignment_source=plan.assignment_source,
				plan_action=plan.action,
				plan_error=plan.reason if plan.action == "ERROR" else None,
				is_off=plan.action == "OFF" or not plan.shift_type,
			)
			if plan.shift_type:
				shift_doc = shift_docs[plan.shift_type]
				start_datetime, end_datetime = _nominal_shift_datetimes(work_date, shift_doc)
				window.update(
					shift_doc=shift_doc,
					start_datetime=start_datetime,
					end_datetime=end_datetime,
					actual_start=start_datetime
					- timedelta(minutes=cint(shift_doc.begin_check_in_before_shift_start_time)),
					actual_end=end_datetime
					+ timedelta(minutes=cint(shift_doc.allow_check_out_after_shift_end_time)),
					is_overnight=end_datetime.date() > work_date,
					is_off=False,
				)
			windows[(employee.name, work_date)] = window

	return windows


def load_checkins_for_windows(employees, windows, from_date, to_date):
	"""Load logs once and assign each one to the employee's planned shift.

	The Shift Type buffer remains useful metadata for standard HRMS screens, but
	it is not an ownership boundary here. Each daytime shift owns its calendar
	work date; an overnight shift owns noon-to-noon around its start date. In
	overlapping cycles, a strict IN punch favours the upcoming shift, a strict
	OUT punch favours the previous shift, and alternating devices use the closest
	nominal shift. One log can therefore never be consumed by two work dates.
	"""
	from_date, to_date = getdate(from_date), getdate(to_date)
	employees = [frappe._dict(row) for row in employees]
	employee_names = [row.name for row in employees]
	if not employee_names:
		return defaultdict(list), defaultdict(list)

	# The previous/next work date is required to resolve punches outside the
	# nominal shift without a fixed minute buffer. Most callers intentionally
	# build only their reporting range, so fill the one-day ownership context
	# here and let the caller-supplied windows win inside the requested range.
	context_start = from_date - timedelta(days=1)
	context_end = to_date + timedelta(days=1)
	ownership_windows = dict(windows)
	if any(
		(employee_name, boundary_date) not in ownership_windows
		for employee_name in employee_names
		for boundary_date in (context_start, context_end)
	):
		context_windows = build_shift_windows(employees, context_start, context_end)
		context_windows.update(ownership_windows)
		ownership_windows = context_windows

	target_keys = {
		key
		for key in windows
		if from_date <= getdate(key[1]) <= to_date
	}
	planned_by_employee = defaultdict(list)
	for window in ownership_windows.values():
		if not window.is_off:
			planned_by_employee[window.employee].append(window)
	for employee_windows in planned_by_employee.values():
		employee_windows.sort(key=lambda window: window.start_datetime)

	rows = frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": ["in", employee_names],
			"skip_auto_attendance": 0,
			"time": [
				"between",
				[
					get_datetime(getdate(from_date) - timedelta(days=1)),
					get_datetime(getdate(to_date) + timedelta(days=2)),
				],
			],
			"docstatus": ["<", 2],
		},
		fields=[
			"name",
			"employee",
			"time",
			"log_type",
			"shift",
			"shift_start",
			"shift_end",
			"shift_actual_start",
			"shift_actual_end",
			"offshift",
			"skip_auto_attendance",
			"attendance",
		],
		order_by="employee asc, time asc",
	)
	linked_attendance_dates = {}
	linked_attendance_names = list({row.attendance for row in rows if row.attendance})
	if linked_attendance_names:
		linked_attendance_dates = {
			row.name: getdate(row.attendance_date)
			for row in frappe.get_all(
				"Attendance",
				filters={"name": ["in", linked_attendance_names]},
				fields=["name", "attendance_date"],
			)
		}

	assigned = defaultdict(list)
	unplanned = defaultdict(list)
	for row in rows:
		log_time = get_datetime(row.time)
		linked_work_date = linked_attendance_dates.get(row.attendance)
		if linked_work_date:
			window = ownership_windows.get((row.employee, linked_work_date))
			if (
				not window
				or window.is_off
				or not _is_within_checkin_ownership(log_time, window)
			):
				if from_date <= log_time.date() <= to_date:
					unplanned[(row.employee, log_time.date())].append(row)
				continue
		else:
			window = _select_checkin_window(
				row, planned_by_employee.get(row.employee, [])
			)

		if window and _is_blocked_by_off_date(
			row, window, ownership_windows, linked_work_date=linked_work_date
		):
			window = None

		if not window or (window.employee, window.work_date) not in target_keys:
			if from_date <= log_time.date() <= to_date:
				unplanned[(row.employee, log_time.date())].append(row)
			continue

		row.shift = window.shift_type
		row.shift_start = window.start_datetime
		row.shift_end = window.end_datetime
		row.shift_actual_start = window.actual_start
		row.shift_actual_end = window.actual_end
		assigned[(row.employee, window.work_date)].append(row)

	return assigned, unplanned


def load_holiday_context(employees, windows, from_date, to_date):
	"""Load employee/company/Shift Type Holiday Lists in one batch."""
	company_names = {row.company for row in employees if row.get("company")}
	company_lists = {
		row.name: row.default_holiday_list
		for row in frappe.get_all(
			"Company",
			filters={"name": ["in", list(company_names)]} if company_names else {},
			fields=["name", "default_holiday_list"],
		)
	}
	list_names = {
		row.get("holiday_list") or company_lists.get(row.company)
		for row in employees
	}
	list_names.update(
		window.shift_doc.holiday_list
		for window in windows.values()
		if window.get("shift_doc") and window.shift_doc.holiday_list
	)
	list_names.discard(None)

	holidays = defaultdict(dict)
	if list_names:
		for row in frappe.get_all(
			"Holiday",
			filters={
				"parent": ["in", list(list_names)],
				"holiday_date": ["between", [getdate(from_date), getdate(to_date)]],
			},
			fields=["parent", "holiday_date", "weekly_off", "description"],
		):
			holidays[row.parent][getdate(row.holiday_date)] = row
	return frappe._dict(company_lists=company_lists, holidays=holidays)


def classify_work_date(employee, window, holiday_context):
	"""Return work, off, or holiday for a resolved employee/work date."""
	if not window or window.is_off:
		return "off"

	holiday_list = (
		window.shift_doc.holiday_list
		or employee.get("holiday_list")
		or holiday_context.company_lists.get(employee.company)
	)
	holiday = holiday_context.holidays.get(holiday_list, {}).get(window.work_date)
	if not holiday:
		return "work"

	# Rotating Kíp weekly OFF is defined by VNT Shift Group Schedule. A Sunday
	# in the company Holiday List must not suppress a Kíp that is scheduled.
	if cint(holiday.weekly_off):
		return "work" if window.shift_group else "off"
	return "holiday"


def get_log_presence(window, logs):
	"""Return (has_in, has_out), including a deterministic one-punch rule."""
	logs = sorted(logs or [], key=lambda row: get_datetime(row.time))
	if not logs:
		return False, False

	mode = window.shift_doc.determine_check_in_and_check_out
	if mode == "Strictly based on Log Type in Employee Checkin":
		return (
			any((row.log_type or "").upper() == "IN" for row in logs),
			any((row.log_type or "").upper() == "OUT" for row in logs),
		)

	# Biometric devices are synchronized by calendar day, so their IN/OUT label
	# is not reliable for the after-midnight portion of a night shift. For the
	# configured alternating mode, place punches on either side of the shift
	# midpoint. Multiple duplicate punches near one edge remain a missing punch.
	midpoint = window.start_datetime + (window.end_datetime - window.start_datetime) / 2
	has_in = get_datetime(logs[0].time) <= midpoint
	has_out = get_datetime(logs[-1].time) >= midpoint
	return has_in, has_out


def calculate_attendance_details(window, logs, *, respect_marking_flags=True):
	"""Calculate attendance details using the resolved planned shift window.

	``respect_marking_flags`` keeps the standard Attendance behaviour by default:
	late/early fields are only populated when their Shift Type switches are on.
	Reports can pass ``False`` to compare punches with the planned start/end time
	directly, without enabling HRMS Auto Attendance.
	"""
	logs = sorted(logs or [], key=lambda row: get_datetime(row.time))
	shift_doc = window.shift_doc
	has_in, has_out = get_log_presence(window, logs)

	working_hours = 0.0
	in_time = out_time = None
	if logs:
		working_hours, in_time, out_time = calculate_working_hours(
			logs,
			shift_doc.determine_check_in_and_check_out,
			shift_doc.working_hours_calculation_based_on,
		)

	# Standard alternating logic assumes the first and last rows are a complete
	# pair. Correct that assumption when every punch lies at only one shift edge.
	if not has_in or not has_out:
		working_hours = 0.0
		in_time = get_datetime(logs[0].time) if has_in else None
		out_time = get_datetime(logs[-1].time) if has_out else None

	late_entry = bool(
		(not respect_marking_flags or cint(shift_doc.enable_late_entry_marking))
		and in_time
		and in_time
		> window.start_datetime + timedelta(minutes=cint(shift_doc.late_entry_grace_period))
	)
	early_exit = bool(
		(not respect_marking_flags or cint(shift_doc.enable_early_exit_marking))
		and out_time
		and out_time
		< window.end_datetime - timedelta(minutes=cint(shift_doc.early_exit_grace_period))
	)

	status = "Absent" if not has_in or not has_out else "Present"
	if (
		has_in
		and has_out
		and shift_doc.working_hours_threshold_for_absent
		and flt(working_hours) < flt(shift_doc.working_hours_threshold_for_absent)
	):
		status = "Absent"
	elif (
		has_in
		and has_out
		and shift_doc.working_hours_threshold_for_half_day
		and flt(working_hours) < flt(shift_doc.working_hours_threshold_for_half_day)
	):
		status = "Half Day"

	return frappe._dict(
		status=status,
		working_hours=working_hours,
		in_time=in_time,
		out_time=out_time,
		late_entry=late_entry,
		early_exit=early_exit,
		has_in=has_in,
		has_out=has_out,
	)


def process_attendance(from_date, to_date, *, dry_run=False, employee_names=None):
	"""Create/link Attendance for closed planned shifts in an idempotent pass."""
	from_date, to_date = _validate_range(from_date, to_date)
	employees = get_active_employees(from_date, to_date, employee_names)
	result = {
		"Số Shift Assignment tạo mới": 0,
		"Số Checkin gán lại đúng ca": 0,
		"Số Attendance tạo mới": 0,
		"Số Attendance bổ sung giờ vào/ra": 0,
		"Số ngày nghỉ/không xếp ca bỏ qua": 0,
		"Số ca chưa kết thúc bỏ qua": 0,
		"Số lỗi": 0,
	}
	if not employees:
		return result

	assignment_result = generate_shift_assignments(
		from_date,
		to_date,
		employees=[row.name for row in employees],
		preview=bool(dry_run),
	)
	result["Số Shift Assignment tạo mới"] = cint(
		assignment_result.get("counts", {}).get("CREATE")
	)
	result["Số lỗi"] += cint(assignment_result.get("counts", {}).get("ERROR"))

	# Reload after generation so Checkins and Attendance both use the persisted
	# Shift Assignment that HR can inspect on the Employee timeline.
	windows = build_shift_windows(employees, from_date, to_date)
	checkin_map, _unplanned = load_checkins_for_windows(
		employees, windows, from_date, to_date
	)
	holiday_context = load_holiday_context(employees, windows, from_date, to_date)
	existing_attendance = _load_attendance_map(employees, from_date, to_date)
	employee_map = {row.name: row for row in employees}
	now = now_datetime()

	for key, window in windows.items():
		employee = employee_map[window.employee]
		attendance = existing_attendance.get(key)
		logs = [
			row
			for row in checkin_map.get(key, [])
			if not row.attendance or (attendance and row.attendance == attendance.name)
		]
		day_type = classify_work_date(employee, window, holiday_context)
		if day_type == "off" or (
			day_type == "holiday"
			and (not logs or not cint(window.shift_doc.mark_auto_attendance_on_holidays))
		):
			result["Số ngày nghỉ/không xếp ca bỏ qua"] += 1
			continue
		if not window.get("end_datetime") or window.end_datetime >= now:
			result["Số ca chưa kết thúc bỏ qua"] += 1
			continue

		result["Số Checkin gán lại đúng ca"] += _sync_checkin_shift_fields(
			window, logs, dry_run=dry_run
		)
		if attendance:
			result["Số Attendance bổ sung giờ vào/ra"] += _repair_existing_attendance(
				attendance,
				window,
				logs,
				punches_required=not cint(employee.custom_need_check),
				dry_run=dry_run,
			)
			continue

		details = calculate_attendance_details(window, logs) if logs else frappe._dict(
			status="Present" if cint(employee.custom_need_check) else "Absent",
			working_hours=0,
			in_time=None,
			out_time=None,
			late_entry=False,
			early_exit=False,
		)
		if cint(employee.custom_need_check):
			# This flag means biometric punches are not mandatory. Preserve any
			# available times for information, but never penalize missing punches.
			details.status = "Present"
		if dry_run:
			result["Số Attendance tạo mới"] += 1
			continue

		frappe.db.savepoint("vnt_attendance_row")
		try:
			attendance_doc = frappe.get_doc(
				{
					"doctype": "Attendance",
					"employee": employee.name,
					"attendance_date": window.work_date,
					"status": details.status,
					"shift": window.shift_type,
					"working_hours": details.working_hours,
					"in_time": details.in_time,
					"out_time": details.out_time,
					"late_entry": details.late_entry,
					"early_exit": details.early_exit,
				}
			)
			attendance_doc.flags.ignore_permissions = True
			attendance_doc.insert(ignore_permissions=True)
			attendance_doc.submit()
			linkable_logs = [row.name for row in logs if not row.attendance]
			if linkable_logs:
				update_attendance_in_checkins(linkable_logs, attendance_doc.name)
			result["Số Attendance tạo mới"] += 1
		except Exception:
			frappe.db.rollback(save_point="vnt_attendance_row")
			result["Số lỗi"] += 1
			frappe.log_error(
				frappe.get_traceback(),
				f"VNT Attendance {employee.name} {window.work_date}",
			)

	return result


def _nominal_shift_datetimes(work_date, shift_doc):
	start_time = get_time(shift_doc.start_time)
	end_time = get_time(shift_doc.end_time)
	start_datetime = datetime.combine(getdate(work_date), start_time)
	end_datetime = datetime.combine(getdate(work_date), end_time)
	if end_time <= start_time:
		end_datetime += timedelta(days=1)
	return start_datetime, end_datetime


def _select_checkin_window(row, windows):
	"""Select one planned shift without using the Shift Type minute buffer."""
	if not windows:
		return None

	log_time = get_datetime(row.time)
	windows = sorted(
		(
			window
			for window in windows
			if _is_within_checkin_ownership(log_time, window)
		),
		key=lambda window: window.start_datetime,
	)
	if not windows:
		return None
	nominal = [
		window
		for window in windows
		if window.start_datetime <= log_time <= window.end_datetime
	]
	if nominal:
		return min(
			nominal,
			key=lambda window: abs(
				log_time
				- (
					window.start_datetime
					+ (window.end_datetime - window.start_datetime) / 2
				)
			),
		)

	previous_window = next(
		(window for window in reversed(windows) if window.end_datetime < log_time),
		None,
	)
	next_window = next(
		(window for window in windows if window.start_datetime > log_time),
		None,
	)
	log_type = (row.log_type or "").upper()
	strict_mode = "Strictly based on Log Type in Employee Checkin"
	if (
		log_type == "OUT"
		and previous_window
		and previous_window.shift_doc.determine_check_in_and_check_out == strict_mode
	):
		return previous_window
	if (
		log_type == "IN"
		and next_window
		and next_window.shift_doc.determine_check_in_and_check_out == strict_mode
	):
		return next_window

	candidates = [window for window in (previous_window, next_window) if window]
	return (
		min(
			candidates,
			key=lambda window: (
				_checkin_distance_from_window(log_time, window),
				window.start_datetime,
			),
		)
		if candidates
		else None
	)


def _checkin_ownership_start(window):
	start_of_work_date = get_datetime(window.work_date)
	return (
		start_of_work_date + timedelta(hours=12)
		if window.is_overnight
		else start_of_work_date
	)


def _checkin_ownership_end(window):
	return _checkin_ownership_start(window) + timedelta(days=1)


def _is_within_checkin_ownership(log_time, window):
	return _checkin_ownership_start(window) <= log_time < _checkin_ownership_end(window)


def _checkin_distance_from_window(log_time, window):
	if log_time < window.start_datetime:
		return window.start_datetime - log_time
	if log_time > window.end_datetime:
		return log_time - window.end_datetime
	return timedelta(0)


def _is_blocked_by_off_date(row, window, windows, *, linked_work_date=None):
	"""Keep OFF-day punches unplanned, except the tail of an overnight shift."""
	if linked_work_date:
		return False
	log_time = get_datetime(row.time)
	calendar_window = windows.get((row.employee, log_time.date()))
	if not calendar_window or not calendar_window.is_off:
		return False
	return not (
		window.is_overnight
		and window.end_datetime.date() == log_time.date()
		and log_time >= window.start_datetime
	)


def _load_attendance_map(employees, from_date, to_date):
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
			"shift",
			"working_hours",
			"in_time",
			"out_time",
			"late_entry",
			"early_exit",
			"leave_type",
			"docstatus",
		],
		order_by="docstatus desc, modified desc",
	)
	result = {}
	for row in rows:
		result.setdefault((row.employee, getdate(row.attendance_date)), row)
	return result


def _sync_checkin_shift_fields(window, logs, *, dry_run=False):
	updated = 0
	for row in logs:
		if row.attendance:
			continue
		values = {
			"shift": window.shift_type,
			"shift_start": window.start_datetime,
			"shift_end": window.end_datetime,
			"shift_actual_start": window.actual_start,
			"shift_actual_end": window.actual_end,
			"offshift": 0,
		}
		if all(row.get(fieldname) == value for fieldname, value in values.items()):
			continue
		updated += 1
		if not dry_run:
			frappe.db.set_value(
				"Employee Checkin", row.name, values, update_modified=False
			)
	return updated


def _repair_existing_attendance(
	attendance, window, logs, *, punches_required=True, dry_run=False
):
	if not logs:
		return 0
	if attendance.leave_type or attendance.status not in {"Present", "Absent", "Half Day"}:
		return 0
	if attendance.shift and attendance.shift != window.shift_type:
		# A non-empty different shift is an HR decision or legacy exception. Do
		# not relink its logs automatically; surface it through reconciliation.
		return 0
	details = calculate_attendance_details(window, logs)
	if not punches_required:
		details.status = "Present"
	updates = {}
	if not attendance.shift:
		updates["shift"] = window.shift_type
	if attendance.status != details.status:
		updates["status"] = details.status
	if details.has_in and details.has_out:
		if attendance.in_time != details.in_time:
			updates["in_time"] = details.in_time
		if attendance.out_time != details.out_time:
			updates["out_time"] = details.out_time
	elif details.in_time and not attendance.in_time:
		updates["in_time"] = details.in_time
	elif details.out_time and not attendance.out_time:
		updates["out_time"] = details.out_time
	if abs(flt(attendance.working_hours) - flt(details.working_hours)) > 0.0001:
		updates["working_hours"] = details.working_hours
	if cint(attendance.late_entry) != cint(details.late_entry):
		updates["late_entry"] = cint(details.late_entry)
	if cint(attendance.early_exit) != cint(details.early_exit):
		updates["early_exit"] = cint(details.early_exit)
	linkable_logs = [row.name for row in logs if not row.attendance]
	if not updates and not linkable_logs:
		return 0
	if not dry_run:
		if updates:
			frappe.db.set_value("Attendance", attendance.name, updates, update_modified=False)
		if linkable_logs:
			update_attendance_in_checkins(linkable_logs, attendance.name)
	return 1


def _validate_range(from_date, to_date):
	from_date, to_date = getdate(from_date), getdate(to_date)
	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date."))
	if (to_date - from_date).days + 1 > MAX_MANUAL_GENERATION_DAYS:
		frappe.throw(
			_("Attendance processing range cannot exceed {0} days.").format(
				MAX_MANUAL_GENERATION_DAYS
			)
		)
	return from_date, to_date
