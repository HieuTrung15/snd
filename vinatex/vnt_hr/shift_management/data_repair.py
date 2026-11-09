"""Audited repairs for data produced by the VNT shift engine.

These helpers are intentionally not whitelisted. They are operational tools to
be run by an administrator from ``bench execute`` after a database backup.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, get_time, getdate

from vinatex.vnt_hr.shift_management.constants import AUTO_ASSIGNMENT_SOURCE


def repair_administrative_shift_checkins(
	effective_from="2026-10-01", dry_run=True
) -> dict:
	"""Align stored check-in shift metadata with the 07:30-16:30 master."""
	shift = frappe.get_cached_doc("Shift Type", "Hành chính")
	if (
		get_time(shift.start_time) != get_time("07:30:00")
		or get_time(shift.end_time) != get_time("16:30:00")
		or cint(shift.begin_check_in_before_shift_start_time) != 60
		or cint(shift.allow_check_out_after_shift_end_time) != 60
	):
		frappe.throw(
			_(
				"Shift Type Hành chính must be configured as 07:30-16:30 with 60-minute buffers before this repair can run."
			)
		)

	effective_date = getdate(effective_from)
	effective_datetime = datetime.combine(effective_date, datetime.min.time())
	rows = frappe.get_all(
		"Employee Checkin",
		filters={
			"shift": shift.name,
			"time": [">=", effective_datetime],
			"docstatus": ["<", 2],
		},
		fields=[
			"name",
			"time",
			"shift_start",
			"shift_end",
			"shift_actual_start",
			"shift_actual_end",
			"offshift",
			"attendance",
		],
		order_by="time asc, name asc",
	)

	rows_to_update = 0
	updated_rows = 0
	for row in rows:
		work_date = getdate(row.shift_start or row.time)
		shift_start = datetime.combine(work_date, get_time(shift.start_time))
		shift_end = datetime.combine(work_date, get_time(shift.end_time))
		values = {
			"shift_start": shift_start,
			"shift_end": shift_end,
			"shift_actual_start": shift_start
			- timedelta(minutes=cint(shift.begin_check_in_before_shift_start_time)),
			"shift_actual_end": shift_end
			+ timedelta(minutes=cint(shift.allow_check_out_after_shift_end_time)),
			"offshift": 0,
		}
		if all(
			(cint(row.get(fieldname)) == expected if fieldname == "offshift" else (
				bool(row.get(fieldname)) and get_datetime(row.get(fieldname)) == expected
			))
			for fieldname, expected in values.items()
		):
			continue

		rows_to_update += 1
		if not cint(dry_run):
			frappe.db.set_value(
				"Employee Checkin", row.name, values, update_modified=False
			)
			updated_rows += 1

	return {
		"effective_from": effective_date,
		"dry_run": bool(cint(dry_run)),
		"matched_rows": len(rows),
		"linked_rows": sum(bool(row.attendance) for row in rows),
		"rows_to_update": rows_to_update,
		"updated_rows": updated_rows,
		"already_correct": len(rows) - rows_to_update,
	}


def audit_duplicate_auto_assignments() -> dict:
	"""Describe exact duplicate, non-cancelled, day-level engine assignments."""
	groups = _duplicate_groups()
	conflicts = []
	redundant_rows = 0
	for key, rows in groups.items():
		identities = {
			(
				row.shift_type,
				row.custom_shift_group,
				row.start_date,
				row.end_date,
			)
			for row in rows
		}
		if len(identities) != 1:
			conflicts.append(
				{
					"employee": key[0],
					"date": key[1],
					"assignments": [row.name for row in rows],
				}
			)
			continue
		redundant_rows += len(rows) - 1

	return {
		"duplicate_employee_dates": len(groups),
		"redundant_rows": redundant_rows,
		"affected_employees": len({key[0] for key in groups}),
		"conflicting_employee_dates": len(conflicts),
		"conflicts": conflicts[:20],
	}


def repair_duplicate_auto_assignments(*, dry_run: bool = True) -> dict:
	"""Cancel only exact inactive duplicates while retaining the oldest row.

	HRMS normally blocks cancellation when Attendance/Checkin exists for the same
	employee, date and Shift Type. That protection cannot distinguish one member
	of an exact duplicate set from another, so this repair performs a guarded
	docstatus update after proving that every surplus row has identical business
	meaning and is already expired/Inactive.
	"""
	groups = _duplicate_groups(for_update=not dry_run)
	audit = audit_duplicate_auto_assignments()
	if audit["conflicting_employee_dates"]:
		frappe.throw(
			_("Duplicate Shift Assignments with conflicting business values were found; nothing was changed.")
		)

	blocked = []
	to_cancel = []
	for (employee, work_date), rows in groups.items():
		if any(row.status != "Inactive" or row.docstatus != 1 for row in rows):
			blocked.append(
				{
					"employee": employee,
					"date": work_date,
					"assignments": [row.name for row in rows],
				}
			)
			continue
		# The first persisted row is the canonical plan; later identical rows were
		# created by historical attendance backfills after HRMS expired the first.
		to_cancel.extend(row.name for row in rows[1:])

	if blocked:
		frappe.throw(
			_("Duplicate repair found non-inactive rows; nothing was changed: {0}").format(blocked[:20])
		)

	if not dry_run:
		for assignment_name in to_cancel:
			frappe.db.set_value(
				"Shift Assignment",
				assignment_name,
				{"docstatus": 2, "status": "Inactive"},
				update_modified=True,
			)

	return {
		**audit,
		"dry_run": bool(dry_run),
		"cancelled_rows": 0 if dry_run else len(to_cancel),
		"rows_to_cancel": len(to_cancel),
	}


def _duplicate_groups(*, for_update: bool = False):
	assignment = frappe.qb.DocType("Shift Assignment")
	query = (
		frappe.qb.from_(assignment)
		.select(
			assignment.name,
			assignment.employee,
			assignment.start_date,
			assignment.end_date,
			assignment.shift_type,
			assignment.status,
			assignment.docstatus,
			assignment.creation,
			assignment.custom_shift_group,
		)
		.where(
			(assignment.docstatus < 2)
			& (assignment.custom_generated_by_shift_group == 1)
			& (assignment.custom_assignment_source == AUTO_ASSIGNMENT_SOURCE)
		)
		.orderby(assignment.employee)
		.orderby(assignment.start_date)
		.orderby(assignment.creation)
		.orderby(assignment.name)
	)
	if for_update:
		query = query.for_update()

	grouped = defaultdict(list)
	for row in query.run(as_dict=True):
		grouped[(row.employee, row.start_date)].append(row)
	return {key: rows for key, rows in grouped.items() if len(rows) > 1}
