"""Synchronize the Employee current-group cache from effective memberships."""

from __future__ import annotations

from collections import Counter, defaultdict

import frappe
from frappe import _
from frappe.utils import getdate, today

from vinatex.vnt_hr.shift_management.shift_assignment_service import (
	_lock_employee_rows,
)
from vinatex.vnt_hr.shift_management.work_schedule_filter import (
	get_working_schedule_type_for_shift_group,
)


def get_required_hc_holiday_list(target_shift_group: str) -> str | None:
	"""Return HC's configured Holiday List, or validate that it exists."""
	target_shift_group = str(target_shift_group or "").strip()
	if target_shift_group != "HC":
		return None
	holiday_list = frappe.db.get_value(
		"VNT Shift Group",
		target_shift_group,
		"holiday_list",
	)
	if not holiday_list:
		raise frappe.ValidationError(
		_("Shift Group HC must have a Holiday List before Employees can be transferred to it.")
		)
	return str(holiday_list)


def resolve_active_shift_group(employee: str, as_of_date=None) -> str | None:
	"""Return the single active membership group for an Employee on a date."""
	as_of_date = getdate(as_of_date or today())
	rows = _load_active_memberships([employee], as_of_date).get(employee, [])
	if len(rows) > 1:
		_raise_overlapping_memberships(employee, rows, as_of_date)
	return rows[0].shift_group if rows else None


def sync_employee_current_shift_groups(
	employee_names: list[str] | None = None,
	as_of_date=None,
) -> dict:
	"""Update Employee display fields from memberships effective on ``as_of_date``."""
	as_of_date = getdate(as_of_date or today())
	names = _normalize_employee_names(employee_names)
	filters = {"status": "Active"}
	if names is not None:
		filters["name"] = ["in", names]
	locked_employee_names = sorted(
		frappe.get_all(
			"Employee",
			filters=filters,
			pluck="name",
			order_by="name asc",
		)
	)
	if not locked_employee_names:
		return {
			"status": "COMPLETED",
			"as_of_date": as_of_date.isoformat(),
			"employees": 0,
			"counts": {},
		}
	_lock_employee_rows(locked_employee_names)

	# Re-read both cache and memberships only after taking the same stable
	# Employee locks used by transfer execution. A transfer that committed while
	# this job waited is therefore observed instead of being overwritten.
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active", "name": ["in", locked_employee_names]},
		fields=[
			"name",
			"custom_shift_group",
			"custom_working_schedule_type",
			"holiday_list",
		],
		order_by="name asc",
	)
	employee_names_found = [row.name for row in employees]
	memberships = _load_active_memberships(employee_names_found, as_of_date)
	for employee in employees:
		rows = memberships.get(employee.name, [])
		if len(rows) > 1:
			_raise_overlapping_memberships(employee.name, rows, as_of_date)
	hc_holiday_list = (
		get_required_hc_holiday_list("HC")
		if any(
			rows and rows[0].shift_group == "HC"
			for rows in memberships.values()
		)
		else None
	)
	counts = Counter()
	for employee in employees:
		rows = memberships.get(employee.name, [])
		if not rows:
			counts["SKIPPED_NO_ACTIVE_MEMBERSHIP"] += 1
			continue
		target_group = rows[0].shift_group
		target_schedule_type = get_working_schedule_type_for_shift_group(target_group)
		target_holiday_list = hc_holiday_list if target_group == "HC" else None
		if (
			employee.get("custom_shift_group") == target_group
			and employee.get("custom_working_schedule_type") == target_schedule_type
			and (
				target_group != "HC"
				or employee.get("holiday_list") == target_holiday_list
			)
		):
			counts["UNCHANGED"] += 1
			continue
		values = {
			"custom_shift_group": target_group,
			"custom_working_schedule_type": target_schedule_type,
		}
		if target_group == "HC":
			values["holiday_list"] = target_holiday_list
		frappe.db.set_value(
			"Employee",
			employee.name,
			values,
			update_modified=False,
		)
		counts["UPDATED"] += 1
	return {
		"status": "COMPLETED",
		"as_of_date": as_of_date.isoformat(),
		"employees": len(employees),
		"counts": dict(sorted(counts.items())),
	}


def _normalize_employee_names(employee_names):
	if employee_names is None:
		return None
	if isinstance(employee_names, str):
		employee_names = [employee_names]
	return sorted({str(value) for value in employee_names if value})


def _load_active_memberships(employee_names, as_of_date):
	if not employee_names:
		return defaultdict(list)
	rows = frappe.get_all(
		"VNT Shift Group Assignment",
		filters={
			"employee": ["in", employee_names],
			"status": "Active",
			"from_date": ["<=", as_of_date],
		},
		or_filters=[["to_date", ">=", as_of_date], ["to_date", "is", "not set"]],
		fields=["name", "employee", "shift_group", "from_date", "to_date", "status"],
		order_by="employee asc, from_date asc, name asc",
	)
	result = defaultdict(list)
	for row in rows:
		from_date = getdate(row.from_date)
		to_date = getdate(row.to_date) if row.to_date else None
		if row.status == "Active" and from_date <= as_of_date and (
			not to_date or to_date >= as_of_date
		):
			result[row.employee].append(row)
	return result


def _raise_overlapping_memberships(employee, rows, as_of_date):
	raise frappe.ValidationError(
		_('Employee {0} has overlapping active Shift Group memberships on {1}: {2}.').format(
			employee,
			as_of_date,
			", ".join(row.name for row in rows),
		)
	)
