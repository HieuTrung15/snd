"""Resolve rotating shift groups and weekly schedules without mutating legacy data."""

from __future__ import annotations

from datetime import time, timedelta

import frappe
from frappe.utils import get_datetime, getdate

from vinatex.vnt_hr.shift_management.constants import WEEKDAYS


def _logger():
	return frappe.logger("vnt_shift_management", allow_site=True, file_count=10)


def shift_management_schema_is_ready() -> bool:
	"""Return whether the new schema is installed.

	This guard lets code be deployed before `bench migrate` without breaking an
	already-running scheduler process.
	"""
	return frappe.db.table_exists("VNT Shift Group") and frappe.db.table_exists("VNT Shift Group Assignment")


def get_employee_shift_group(employee: str, on_date=None) -> frappe._dict | None:
	"""Resolve an Employee's Kíp for a date using documented precedence.

	Precedence is effective-dated assignment, Employee custom field, then an
	exact-name legacy Default Shift match. The legacy branch is deliberately
	read-only: this function never saves or updates Employee.
	"""
	if not shift_management_schema_is_ready():
		return None

	on_date = getdate(on_date)
	assignment = frappe.qb.DocType("VNT Shift Group Assignment")
	assignments = (
		frappe.qb.from_(assignment)
		.select(assignment.name, assignment.shift_group, assignment.company, assignment.from_date)
		.where(
			(assignment.employee == employee)
			& (assignment.status == "Active")
			& (assignment.from_date <= on_date)
			& (assignment.to_date.isnull() | (assignment.to_date >= on_date))
		)
		.orderby(assignment.from_date, order=frappe.qb.desc)
	).run(as_dict=True)
	if assignments:
		if len(assignments) > 1:
			_logger().warning(
				"Overlapping VNT Shift Group Assignment detected for employee=%s date=%s records=%s",
				employee,
				on_date,
				[row.name for row in assignments],
			)
		if _is_group_available(assignments[0].shift_group, assignments[0].company, on_date):
			return frappe._dict(
				shift_group=assignments[0].shift_group,
				source="VNT Shift Group Assignment",
				reference=assignments[0].name,
			)
		_logger().warning(
			"Shift Group Assignment points to an unavailable group employee=%s date=%s group=%s",
			employee,
			on_date,
			assignments[0].shift_group,
		)
		return None

	fields = ["name", "company", "default_shift"]
	if frappe.get_meta("Employee").has_field("custom_shift_group"):
		fields.append("custom_shift_group")
	employee_row = frappe.db.get_value("Employee", employee, fields, as_dict=True)
	if not employee_row:
		return None

	custom_group = employee_row.get("custom_shift_group")
	if custom_group and _is_group_available(custom_group, employee_row.company, on_date):
		return frappe._dict(
			shift_group=custom_group,
			source="Employee.custom_shift_group",
			reference=employee,
		)

	# Legacy compatibility fallback. An exact master-name match is required so a
	# normal Default Shift such as "Hành chính" never becomes a rotating Kíp.
	legacy_group = employee_row.default_shift
	if legacy_group and _is_group_available(legacy_group, employee_row.company, on_date):
		_logger().debug("Legacy Default Shift fallback used for employee=%s group=%s", employee, legacy_group)
		return frappe._dict(
			shift_group=legacy_group,
			source="Employee.default_shift (legacy read-only)",
			reference=employee,
		)

	return None


def get_shift_group_schedule(shift_group: str, on_date=None) -> frappe._dict | None:
	"""Return the schedule row for the date's weekday."""
	on_date = getdate(on_date)
	weekday = WEEKDAYS[on_date.weekday()]
	row = frappe.db.get_value(
		"VNT Shift Group Schedule",
		{"parent": shift_group, "parenttype": "VNT Shift Group", "day_of_week": weekday},
		["day_of_week", "shift_type", "is_off", "sequence"],
		as_dict=True,
	)
	return frappe._dict(row) if row else None


def get_planned_shift(employee: str, on_date=None) -> frappe._dict:
	"""Resolve a day using existing Shift Assignment before Kíp schedule."""
	on_date = getdate(on_date)
	existing = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": employee,
			"start_date": ["<=", on_date],
			"docstatus": ["<", 2],
		},
		or_filters=[["end_date", ">=", on_date], ["end_date", "is", "not set"]],
		fields=["name", "shift_type", "docstatus"],
		order_by="docstatus desc, creation desc",
		limit=1,
	)
	if existing:
		return frappe._dict(
			shift_type=existing[0].shift_type,
			is_off=False,
			source="Shift Assignment",
			reference=existing[0].name,
		)

	resolution = get_employee_shift_group(employee, on_date)
	if not resolution:
		return frappe._dict()
	schedule = get_shift_group_schedule(resolution.shift_group, on_date)
	if not schedule:
		return frappe._dict(
			shift_group=resolution.shift_group,
			source=resolution.source,
			error="MISSING_SCHEDULE",
		)
	return frappe._dict(
		shift_group=resolution.shift_group,
		shift_type=schedule.shift_type,
		is_off=bool(schedule.is_off),
		source=resolution.source,
		reference=resolution.reference,
	)


def is_employee_managed_by_shift_group(employee: str, on_date=None) -> bool:
	"""Used by legacy attendance code to avoid hardcoding Kíp workers as office staff."""
	return bool(get_employee_shift_group(employee, on_date))


def get_managed_employee_dates(employee_names, from_date, to_date) -> set[tuple[str, object]]:
	"""Batch-resolve dates managed by the Kíp engine for legacy job guards."""
	if not employee_names or not shift_management_schema_is_ready():
		return set()

	from_date, to_date = getdate(from_date), getdate(to_date)
	fields = ["name", "company", "default_shift"]
	if frappe.get_meta("Employee").has_field("custom_shift_group"):
		fields.append("custom_shift_group")
	employees = frappe.get_all("Employee", filters={"name": ["in", list(employee_names)]}, fields=fields)
	groups = {
		row.name: row
		for row in frappe.get_all(
			"VNT Shift Group",
			fields=["name", "company", "effective_from", "effective_to", "disabled"],
		)
	}
	memberships: dict[str, list] = {}
	for row in frappe.get_all(
		"VNT Shift Group Assignment",
		filters={
			"employee": ["in", list(employee_names)],
			"status": "Active",
			"from_date": ["<=", to_date],
		},
		or_filters=[["to_date", ">=", from_date], ["to_date", "is", "not set"]],
		fields=["employee", "company", "shift_group", "from_date", "to_date"],
		order_by="employee asc, from_date desc",
	):
		memberships.setdefault(row.employee, []).append(row)

	managed_dates = set()
	current_date = from_date
	while current_date <= to_date:
		for employee in employees:
			active_assignment = next(
				(
					row
					for row in memberships.get(employee.name, [])
					if getdate(row.from_date) <= current_date
					and (not row.to_date or current_date <= getdate(row.to_date))
				),
				None,
			)
			candidate = (
				active_assignment.shift_group
				if active_assignment
				else employee.get("custom_shift_group") or employee.default_shift
			)
			group = groups.get(candidate)
			if group and _group_row_is_available(group, employee.company, current_date):
				managed_dates.add((employee.name, current_date))
		current_date += timedelta(days=1)
	return managed_dates


def get_work_date_for_checkin(
	checkin_datetime,
	*,
	shift_start=None,
	shift_start_time: time | None = None,
	shift_end_time: time | None = None,
):
	"""Return the work date, including the after-midnight part of a night shift.

	HRMS normally persists `Employee Checkin.shift_start`; its date is always the
	best source. The fallback exists for reporting old/unlinked logs only. For a
	22:00-06:00 shift, a 02:00 check-in belongs to the previous calendar day.
	No Employee Checkin is modified by this utility.
	"""
	if shift_start:
		return get_datetime(shift_start).date()

	checkin_datetime = get_datetime(checkin_datetime)
	if shift_start_time and shift_end_time and shift_start_time > shift_end_time:
		if checkin_datetime.time() <= shift_end_time:
			return checkin_datetime.date() - timedelta(days=1)
	return checkin_datetime.date()


def _is_group_available(shift_group: str, company: str, on_date) -> bool:
	group = frappe.db.get_value(
		"VNT Shift Group",
		shift_group,
		["company", "effective_from", "effective_to", "disabled"],
		as_dict=True,
	)
	return _group_row_is_available(group, company, on_date)


def _group_row_is_available(group, company: str, on_date) -> bool:
	if not group or group.disabled or group.company != company:
		return False
	if group.effective_from and getdate(on_date) < getdate(group.effective_from):
		return False
	if group.effective_to and getdate(on_date) > getdate(group.effective_to):
		return False
	return True
