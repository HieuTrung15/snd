"""Daily reconciliation of planned shift, raw check-ins and final Attendance."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_datetime, getdate, time_diff_in_hours

from vinatex.vnt_hr.shift_management.constants import MAX_MANUAL_GENERATION_DAYS
from vinatex.vnt_hr.shift_management.shift_assignment_service import (
	_date_range,
	_load_generation_context,
	_plan_employee_date,
)
from vinatex.vnt_hr.attendance_processing import (
	build_shift_windows,
	calculate_attendance_details,
	load_checkins_for_windows,
)
from vinatex.vnt_hr.shift_management.shift_group_service import get_work_date_for_checkin

ATTENDANCE_NOT_CREATED = "Not Created"
ATTENDANCE_NOT_REQUIRED = "Not Required (Shift OFF)"
ATTENDANCE_DRAFT = "Draft Attendance"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = _validate_filters(filters)
	employees = _get_employees(filters)
	if not employees:
		return get_columns(), []

	context = _load_generation_context(employees, from_date, to_date)
	attendance_map = _get_attendance_map(employees, from_date, to_date)
	leave_map = _get_leave_map(employees, from_date, to_date)
	shift_windows = build_shift_windows(employees, from_date, to_date, context=context)
	checkin_map, unplanned_checkins = load_checkins_for_windows(
		employees, shift_windows, from_date, to_date
	)
	for key, rows in unplanned_checkins.items():
		if from_date <= key[1] <= to_date:
			checkin_map[key].extend(rows)
	holiday_map = _get_holiday_map(employees, context, from_date, to_date)

	data = []
	for employee in employees:
		for work_date in _date_range(from_date, to_date):
			# The shared planning service returns a plain dict because the generator
			# serializes it directly. Wrap it locally so report code can safely use
			# Frappe's attribute-style access (plan.action, plan.shift_type, ...).
			plan = frappe._dict(_plan_employee_date(employee, work_date, context, filters.get("shift_group")))
			if plan.action == "SKIP_FILTER":
				continue

			# Employees outside the rotating model retain standard ERPNext Default
			# Shift behavior; the report displays it but never creates an assignment.
			if plan.action == "SKIP_NO_GROUP" and employee.default_shift:
				plan.shift_type = employee.default_shift
				plan.assignment_source = "Employee.default_shift"

			if filters.get("shift_type") and plan.shift_type != filters.shift_type:
				continue

			attendance = attendance_map.get((employee.name, work_date))
			display_attendance_status = _get_display_attendance_status(plan, attendance)
			if filters.get("attendance_status") and (display_attendance_status != filters.attendance_status):
				continue

			checkins = checkin_map.get((employee.name, work_date), [])
			window = shift_windows.get((employee.name, work_date))
			leave = leave_map.get((employee.name, work_date))
			details = (
				calculate_attendance_details(window, checkins)
				if window and not window.is_off and checkins
				else None
			)
			in_time = attendance.in_time if attendance and attendance.in_time else (
				details.in_time if details else _first_checkin(checkins)
			)
			out_time = attendance.out_time if attendance and attendance.out_time else (
				details.out_time if details else _last_checkin(checkins)
			)
			working_hours = attendance.working_hours if attendance else None
			if working_hours is None or (not flt(working_hours) and details and details.working_hours):
				working_hours = details.working_hours if details else _calculate_actual_hours(in_time, out_time)
			holiday_status = _holiday_status(employee, plan, work_date, context, holiday_map)

			data.append(
				{
					"employee": employee.name,
					"employee_name": employee.employee_name,
					"department": employee.department,
					"designation": employee.designation,
					"shift_group": plan.shift_group,
					"attendance_date": work_date,
					"planned_shift": plan.shift_type,
					"shift_type": _actual_shift(attendance, checkins),
					# Query Report's Time formatter expects a time value, not a full
					# Datetime. Passing Datetime produced incorrect hours in the UI.
					"in_time": _format_time(in_time),
					"out_time": _format_time(out_time),
					"working_hours": working_hours,
					"attendance_status": display_attendance_status,
					"late_entry": bool(attendance and attendance.late_entry)
					or bool(details and details.late_entry),
					"early_exit": bool(attendance and attendance.early_exit)
					or bool(details and details.early_exit),
					"leave_type": (attendance.leave_type if attendance else None)
					or (leave.leave_type if leave else None),
					"holiday_status": holiday_status,
					"assignment_source": plan.assignment_source,
					"note": _build_note(plan, attendance, leave),
				}
			)

	return get_columns(), data


def get_columns():
	return [
		# {
		# 	"label": _("Employee"),
		# 	"fieldname": "employee",
		# 	"fieldtype": "Link",
		# 	"options": "Employee",
		# 	"width": 120,
		# },
		{"label": _("Tên nhân viên"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		# {
		# 	"label": _("Department"),
		# 	"fieldname": "department",
		# 	"fieldtype": "Link",
		# 	"options": "Department",
		# 	"width": 160,
		# },
		# {
		# 	"label": _("Designation"),
		# 	"fieldname": "designation",
		# 	"fieldtype": "Link",
		# 	"options": "Designation",
		# 	"width": 140,
		# },
		{
			"label": _("Kíp"),
			"fieldname": "shift_group",
			"fieldtype": "Link",
			"options": "VNT Shift Group",
			"width": 100,
		},
		{
			"label": _("Kế hoạch"),
			"fieldname": "planned_shift",
			"fieldtype": "Link",
			"options": "Shift Type",
			"width": 120,
		},
		{
			"label": _("Thực tế"),
			"fieldname": "shift_type",
			"fieldtype": "Link",
			"options": "Shift Type",
			"width": 130,
		},
		{"label": _("Ngày"), "fieldname": "attendance_date", "fieldtype": "Date", "width": 100},
		{"label": _("Giờ vào"), "fieldname": "in_time", "fieldtype": "Time", "width": 155},
		{"label": _("Giờ ra"), "fieldname": "out_time", "fieldtype": "Time", "width": 155},
		{"label": _("Số giờ làm việc"), "fieldname": "working_hours", "fieldtype": "Float", "width": 110},
		{
			"label": _("Trạng thái chấm công"),
			"fieldname": "attendance_status",
			"fieldtype": "Data",
			"width": 175,
			"description": _(
				"Trạng thái của Attendance đã trình. Chưa tạo Attendance nghĩa là có thể đã có Checkin nhưng chưa có bản ghi Attendance."
			),
		},
		{"label": _("Đi trễ"), "fieldname": "late_entry", "fieldtype": "Check", "width": 85},
		{"label": _("Về sớm"), "fieldname": "early_exit", "fieldtype": "Check", "width": 85},
		{
			"label": _("Loại nghỉ"),
			"fieldname": "leave_type",
			"fieldtype": "Link",
			"options": "Leave Type",
			"width": 130,
		},
		{"label": _("Ngày nghỉ / Nghỉ kíp"), "fieldname": "holiday_status", "fieldtype": "Data", "width": 140},
		# {
		# 	"label": _("Assignment Source"),
		# 	"fieldname": "assignment_source",
		# 	"fieldtype": "Data",
		# 	"width": 150,
		# },
		# {"label": _("Ghi chú"), "fieldname": "note", "fieldtype": "Data", "width": 240},
	]


def _validate_filters(filters):
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are required."))
	from_date, to_date = getdate(filters.from_date), getdate(filters.to_date)
	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date."))
	if (to_date - from_date).days + 1 > MAX_MANUAL_GENERATION_DAYS:
		frappe.throw(_("Report range cannot exceed {0} days.").format(MAX_MANUAL_GENERATION_DAYS))
	return from_date, to_date


def _get_employees(filters):
	fields = [
		"name",
		"employee_name",
		"company",
		"department",
		"designation",
		"holiday_list",
		"default_shift",
	]
	if frappe.get_meta("Employee").has_field("custom_shift_group"):
		fields.append("custom_shift_group")
	db_filters = {}
	for fieldname in ("company", "department", "employee"):
		if filters.get(fieldname):
			db_filters["name" if fieldname == "employee" else fieldname] = filters.get(fieldname)
	# Respect Employee user permissions for interactive HR User reports. All
	# downstream batch queries are constrained to this already-authorized set.
	return frappe.get_list("Employee", filters=db_filters, fields=fields, order_by="name")


def _get_attendance_map(employees, from_date, to_date):
	rows = frappe.get_all(
		"Attendance",
		filters={
			"employee": ["in", [employee.name for employee in employees]],
			"attendance_date": ["between", [from_date, to_date]],
			"docstatus": ["<", 2],
		},
		fields=[
			"name",
			"employee",
			"attendance_date",
			"status",
			"shift",
			"in_time",
			"out_time",
			"working_hours",
			"late_entry",
			"early_exit",
			"leave_type",
			"docstatus",
		],
		order_by="docstatus desc, modified desc",
	)
	return {(row.employee, getdate(row.attendance_date)): row for row in reversed(rows)}


def _get_leave_map(employees, from_date, to_date):
	rows = frappe.get_all(
		"Leave Application",
		filters={
			"employee": ["in", [employee.name for employee in employees]],
			"docstatus": 1,
			"status": "Approved",
			"from_date": ["<=", to_date],
			"to_date": [">=", from_date],
		},
		fields=["employee", "leave_type", "from_date", "to_date", "half_day", "half_day_date"],
	)
	result = {}
	for row in rows:
		for leave_date in _date_range(
			max(getdate(row.from_date), from_date), min(getdate(row.to_date), to_date)
		):
			result.setdefault((row.employee, leave_date), row)
	return result


def _get_checkin_map(employees, from_date, to_date):
	rows = frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": ["in", [employee.name for employee in employees]],
			"time": [
				"between",
				[get_datetime(add_days(from_date, -1)), get_datetime(add_days(to_date, 2))],
			],
			"docstatus": ["<", 2],
		},
		fields=[
			"employee",
			"time",
			"log_type",
			"shift",
			"shift_start",
			"shift_end",
			"shift_actual_start",
			"shift_actual_end",
			"attendance",
		],
		order_by="employee asc, time asc",
	)
	shift_names = {row.shift for row in rows if row.shift}
	shift_times = {}
	if shift_names:
		shift_times = {
			row.name: row
			for row in frappe.get_all(
				"Shift Type",
				filters={"name": ["in", list(shift_names)]},
				fields=["name", "start_time", "end_time"],
			)
		}
	result = defaultdict(list)
	for row in rows:
		shift_type = shift_times.get(row.shift)
		work_date = get_work_date_for_checkin(
			row.time,
			shift_start=row.shift_start or row.shift_actual_start,
			shift_start_time=shift_type.start_time if shift_type else None,
			shift_end_time=shift_type.end_time if shift_type else None,
		)
		if from_date <= work_date <= to_date:
			result[(row.employee, work_date)].append(row)
	return result


def _get_holiday_map(employees, context, from_date, to_date):
	company_names = {employee.company for employee in employees if employee.company}
	company_holidays = {
		row.name: row.default_holiday_list
		for row in frappe.get_all(
			"Company",
			filters={"name": ["in", list(company_names)]},
			fields=["name", "default_holiday_list"],
		)
	}
	list_names = {employee.holiday_list or company_holidays.get(employee.company) for employee in employees}
	list_names.update(group.holiday_list for group in context["groups"].values())
	list_names.discard(None)
	result = defaultdict(set)
	if list_names:
		for row in frappe.get_all(
			"Holiday",
			filters={
				"parent": ["in", list(list_names)],
				"holiday_date": ["between", [from_date, to_date]],
			},
			fields=["parent", "holiday_date"],
		):
			result[row.parent].add(getdate(row.holiday_date))
	result["__company_holidays__"] = company_holidays
	return result


def _holiday_status(employee, plan, work_date, context, holiday_map):
	if plan.action == "OFF":
		return "Nghỉ Kíp"
	group = context["groups"].get(plan.shift_group)
	if group and group.holiday_list and work_date in holiday_map.get(group.holiday_list, set()):
		return "Ngày nghỉ Kíp"
	company_holidays = holiday_map.get("__company_holidays__", {})
	holiday_list = employee.holiday_list or company_holidays.get(employee.company)
	if holiday_list and work_date in holiday_map.get(holiday_list, set()):
		return "Ngày nghỉ/Lễ"
	return None


def _first_checkin(checkins):
	return checkins[0].time if checkins else None


def _last_checkin(checkins):
	return checkins[-1].time if len(checkins) > 1 else None


def _calculate_actual_hours(in_time, out_time):
	if not in_time or not out_time:
		return 0
	return flt(time_diff_in_hours(out_time, in_time), 2)


def _format_time(value):
	if not value:
		return None
	return get_datetime(value).strftime("%H:%M:%S")


def _get_display_attendance_status(plan, attendance):
	if plan.action == "OFF" and (not attendance or attendance.status == "Absent"):
		# OFF means no duty. Preserve an existing Absent source record for audit,
		# but do not present it as a valid absence in the operational day sheet.
		return ATTENDANCE_NOT_REQUIRED
	if not attendance:
		return ATTENDANCE_NOT_CREATED
	if attendance.docstatus == 0:
		return ATTENDANCE_DRAFT
	return attendance.status


def _actual_shift(attendance, checkins):
	if attendance and attendance.shift:
		return attendance.shift
	return next((row.shift for row in checkins if row.shift), None)


def _build_note(plan, attendance, leave):
	notes = []
	if plan.action in ("ERROR", "SKIP_MANUAL") and plan.reason:
		notes.append(plan.reason)
	if leave and not attendance:
		notes.append(_("Approved leave; Attendance not created yet."))
	if plan.action == "OFF" and attendance and attendance.status == "Absent":
		notes.append(_("Existing Absent conflicts with Shift Group OFF; source record was not changed."))
	return " ".join(notes)
