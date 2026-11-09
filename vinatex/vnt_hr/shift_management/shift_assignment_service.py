"""Batch preview and generation of standard HRMS Shift Assignments."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, getdate

from vinatex.vnt_hr.shift_management.constants import (
	AUTO_ASSIGNMENT_SOURCE,
	MAX_MANUAL_GENERATION_DAYS,
	MAX_PREVIEW_ROWS,
	SUNDAY_WORKDAY_DEPARTMENTS,
	SUNDAY_WORKDAY_SHIFT_GROUP,
	WEEKDAYS,
)
from vinatex.vnt_hr.shift_management.shift_group_service import shift_management_schema_is_ready


def _logger():
	return frappe.logger("vnt_shift_management", allow_site=True, file_count=10)


@frappe.whitelist()
def preview_shift_assignments_api(from_date, to_date, shift_group=None, employee=None):
	"""Permission-protected, read-only preview for HR administrators."""
	_require_shift_generation_role()
	return generate_shift_assignments(
		from_date,
		to_date,
		employees=[employee] if employee else None,
		shift_group=shift_group,
		preview=True,
	)


@frappe.whitelist()
def generate_shift_assignments_api(from_date, to_date, shift_group=None, employee=None):
	"""Generate only missing assignments after explicit confirmation in the UI."""
	_require_shift_generation_role()
	return generate_shift_assignments(
		from_date,
		to_date,
		employees=[employee] if employee else None,
		shift_group=shift_group,
		preview=False,
	)


def generate_shift_assignments(
	from_date,
	to_date,
	*,
	employees: Iterable[str] | None = None,
	shift_group: str | None = None,
	preview: bool = False,
) -> dict:
	"""Preview or create idempotent day-level Shift Assignments.

	Every existing non-cancelled Shift Assignment wins. ``Inactive`` is the normal
	HRMS state for an expired assignment, not evidence that the planned day is
	missing. Records without the exact engine
	marker are treated as manual/legacy and are never updated or deleted. Queries
	for employees, memberships, schedules and existing assignments are batched;
	only the required new documents go through the normal Frappe validation API.
	"""
	if not shift_management_schema_is_ready():
		return _empty_result("Shift management schema is not installed yet.")

	from_date, to_date = _validate_date_range(from_date, to_date)
	employee_rows = _get_employees(employees)
	if not employee_rows:
		return _empty_result("No active Employee matched the filters.")

	if not preview:
		_lock_employee_rows([row.name for row in employee_rows])

	context = _load_generation_context(employee_rows, from_date, to_date)
	result_rows: list[dict] = []
	counts: Counter = Counter()
	legacy_employees: set[str] = set()
	truncated = False

	for employee_row in employee_rows:
		for schedule_date in _date_range(from_date, to_date):
			row = _plan_employee_date(employee_row, schedule_date, context, shift_group)
			action = row["action"]

			if action == "CREATE" and not preview:
				frappe.db.savepoint("vnt_shift_assignment_row")
				try:
					assignment_name = _create_shift_assignment(row)
					row["shift_assignment"] = assignment_name
				except Exception as exc:
					frappe.db.rollback(save_point="vnt_shift_assignment_row")
					row["action"] = "ERROR"
					row["reason"] = str(exc)
					_logger().exception(
						"Could not generate Shift Assignment employee=%s date=%s",
						employee_row.name,
						schedule_date,
					)

			counts[row["action"]] += 1
			if row.get("group_source") == "Employee.default_shift (legacy read-only)":
				legacy_employees.add(employee_row.name)
			if len(result_rows) < MAX_PREVIEW_ROWS:
				result_rows.append(row)
			else:
				truncated = True

	return {
		"from_date": from_date,
		"to_date": to_date,
		"preview": preview,
		"counts": dict(counts),
		"rows": result_rows,
		"rows_truncated": truncated,
		"data_changed": not preview and bool(counts.get("CREATE")),
		"diagnostics": {"legacy_fallback_employees": len(legacy_employees)},
	}


def _plan_employee_date(employee, schedule_date, context, requested_group=None) -> dict:
	base = {
		"employee": employee.name,
		"employee_name": employee.employee_name,
		"date": schedule_date,
		"shift_group": None,
		"shift_type": None,
		"action": "ERROR",
		"reason": None,
		"assignment_source": None,
		"group_source": None,
	}

	resolution = _resolve_group_from_context(employee, schedule_date, context)
	resolved_group = resolution.shift_group if resolution else None
	base["group_source"] = resolution.source if resolution else None
	if requested_group and resolved_group != requested_group:
		base.update(
			shift_group=resolved_group,
			action="SKIP_FILTER",
			reason="Resolved Shift Group does not match the requested filter.",
		)
		return base

	existing = context["existing_assignments"].get((employee.name, schedule_date))
	if (
		existing
		and employee.get("department") not in SUNDAY_WORKDAY_DEPARTMENTS
		and _is_department_sunday_policy_assignment(
			existing, employee, schedule_date, context
		)
	):
		existing = None
	if existing:
		base.update(
			shift_type=existing.shift_type,
			shift_group=existing.get("custom_shift_group") or resolved_group,
			shift_assignment=existing.name,
			action="SKIP_EXISTING" if _is_engine_assignment(existing) else "SKIP_MANUAL",
			reason="A non-cancelled Shift Assignment already covers this date.",
			assignment_source=existing.get("custom_assignment_source") or "Legacy/Manual",
		)
		return base

	if not resolution:
		base.update(action="SKIP_NO_GROUP", reason="Employee has no Shift Group for this date.")
		return base
	if resolution.source.startswith("ERROR_OVERLAPPING_GROUP_ASSIGNMENTS"):
		base.update(shift_group=resolution.shift_group, action="ERROR", reason=resolution.source)
		return base

	base["shift_group"] = resolution.shift_group
	group = context["groups"].get(resolution.shift_group)
	if not _group_is_effective(group, employee.company, schedule_date):
		base.update(
			action="ERROR",
			reason="Shift Group is disabled, outside its effective period, or Company differs.",
		)
		return base

	weekday = WEEKDAYS[schedule_date.weekday()]
	schedule = context["schedules"].get((resolution.shift_group, weekday))
	if not schedule:
		base.update(action="ERROR", reason=f"Missing schedule row for {weekday}.")
		return base
	if cint(schedule.is_off):
		if (
			weekday == "Sunday"
			and resolution.shift_group == SUNDAY_WORKDAY_SHIFT_GROUP
			and employee.get("department") in SUNDAY_WORKDAY_DEPARTMENTS
			and employee.get("default_shift") in context["shift_types"]
		):
			base.update(
				shift_type=employee.default_shift,
				action="CREATE",
				reason="Department Sunday workday policy.",
				assignment_source=AUTO_ASSIGNMENT_SOURCE,
			)
			return base
		base.update(action="OFF", reason="Shift Group weekly OFF day.")
		return base
	if not schedule.shift_type or schedule.shift_type not in context["shift_types"]:
		base.update(action="ERROR", reason="Schedule references a missing Shift Type.")
		return base

	base.update(
		shift_type=schedule.shift_type,
		action="CREATE",
		reason=resolution.source,
		assignment_source=AUTO_ASSIGNMENT_SOURCE,
	)
	return base


def _load_generation_context(employee_rows, from_date, to_date) -> dict:
	employee_names = [row.name for row in employee_rows]

	group_rows = frappe.get_all(
		"VNT Shift Group",
		fields=["name", "company", "holiday_list", "effective_from", "effective_to", "disabled"],
	)
	groups = {row.name: row for row in group_rows}

	schedule_rows = []
	if groups:
		schedule_rows = frappe.get_all(
			"VNT Shift Group Schedule",
			filters={"parent": ["in", list(groups)]},
			fields=["parent", "day_of_week", "shift_type", "is_off"],
		)
	schedules = {(row.parent, row.day_of_week): row for row in schedule_rows}
	shift_types = set(frappe.get_all("Shift Type", pluck="name"))

	memberships = defaultdict(list)
	for row in frappe.get_all(
		"VNT Shift Group Assignment",
		filters={
			"employee": ["in", employee_names],
			"status": "Active",
			"from_date": ["<=", to_date],
		},
		or_filters=[["to_date", ">=", from_date], ["to_date", "is", "not set"]],
		fields=["name", "employee", "shift_group", "company", "from_date", "to_date"],
		order_by="employee asc, from_date desc",
	):
		memberships[row.employee].append(row)

	existing_assignments = _load_existing_assignments(employee_names, from_date, to_date)
	return {
		"groups": groups,
		"schedules": schedules,
		"shift_types": shift_types,
		"memberships": memberships,
		"existing_assignments": existing_assignments,
	}


def _load_existing_assignments(employee_names, from_date, to_date) -> dict:
	fields = ["name", "employee", "shift_type", "start_date", "end_date", "docstatus", "status"]
	for custom_field in (
		"custom_assignment_source",
		"custom_shift_group",
		"custom_generated_by_shift_group",
	):
		if frappe.get_meta("Shift Assignment").has_field(custom_field):
			fields.append(custom_field)

	rows = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": ["in", employee_names],
			"start_date": ["<=", to_date],
			"docstatus": ["<", 2],
		},
		or_filters=[["end_date", ">=", from_date], ["end_date", "is", "not set"]],
		fields=fields,
		order_by="docstatus desc, creation asc",
	)

	existing_by_date = {}
	for row in rows:
		row_end = min(getdate(row.end_date) if row.end_date else to_date, to_date)
		row_start = max(getdate(row.start_date), from_date)
		for covered_date in _date_range(row_start, row_end):
			# Existing data can already contain multiple assignments. Preserve all of
			# it and deterministically use the first row only to classify the skip.
			existing_by_date.setdefault((row.employee, covered_date), row)
	return existing_by_date


def _resolve_group_from_context(employee, schedule_date, context) -> frappe._dict | None:
	active_memberships = [
		row
		for row in context["memberships"].get(employee.name, [])
		if getdate(row.from_date) <= schedule_date
		and (not row.to_date or schedule_date <= getdate(row.to_date))
	]
	if active_memberships:
		if len(active_memberships) > 1:
			return frappe._dict(
				shift_group=active_memberships[0].shift_group,
				source=f"ERROR_OVERLAPPING_GROUP_ASSIGNMENTS:{','.join(row.name for row in active_memberships)}",
			)
		return frappe._dict(
			shift_group=active_memberships[0].shift_group,
			source="VNT Shift Group Assignment",
		)

	custom_group = employee.get("custom_shift_group")
	if custom_group and _group_is_effective(
		context["groups"].get(custom_group), employee.company, schedule_date
	):
		return frappe._dict(shift_group=custom_group, source="Employee.custom_shift_group")

	# Legacy compatibility fallback is read-only. Exact membership in the Kíp
	# master set prevents ordinary Default Shift values from entering this engine.
	if employee.default_shift and _group_is_effective(
		context["groups"].get(employee.default_shift), employee.company, schedule_date
	):
		return frappe._dict(
			shift_group=employee.default_shift,
			source="Employee.default_shift (legacy read-only)",
		)
	return None


def _get_employees(employee_names=None):
	fields = ["name", "employee_name", "company", "department", "designation", "default_shift"]
	if frappe.get_meta("Employee").has_field("custom_shift_group"):
		fields.append("custom_shift_group")
	filters = {"status": "Active"}
	if employee_names:
		if isinstance(employee_names, str):
			employee_names = [employee_names]
		filters["name"] = ["in", list(employee_names)]
	return frappe.get_all("Employee", filters=filters, fields=fields, order_by="name")


def _create_shift_assignment(row: dict) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Shift Assignment",
			"employee": row["employee"],
			"shift_type": row["shift_type"],
			"start_date": row["date"],
			"end_date": row["date"],
			"status": "Active",
			"custom_assignment_source": AUTO_ASSIGNMENT_SOURCE,
			"custom_shift_group": row["shift_group"],
			"custom_generated_by_shift_group": 1,
			"custom_schedule_date": row["date"],
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc.name


def _is_engine_assignment(assignment) -> bool:
	return bool(
		cint(assignment.get("custom_generated_by_shift_group"))
		and assignment.get("custom_assignment_source") == AUTO_ASSIGNMENT_SOURCE
	)


def _is_department_sunday_policy_assignment(
	assignment, employee, schedule_date, context
) -> bool:
	"""Identify an engine row created only to override HC's weekly Sunday OFF."""
	if schedule_date.weekday() != 6 or not _is_engine_assignment(assignment):
		return False
	shift_group = assignment.get("custom_shift_group")
	if shift_group != SUNDAY_WORKDAY_SHIFT_GROUP:
		return False
	schedule = context["schedules"].get((shift_group, "Sunday"))
	return bool(
		schedule
		and cint(schedule.is_off)
		and assignment.get("shift_type") == employee.get("default_shift")
	)


def _group_is_effective(group, company, schedule_date) -> bool:
	if not group or cint(group.disabled) or group.company != company:
		return False
	if group.effective_from and schedule_date < getdate(group.effective_from):
		return False
	if group.effective_to and schedule_date > getdate(group.effective_to):
		return False
	return True


def _lock_employee_rows(employee_names):
	"""Serialize generators for the same Employees without a risky DB constraint."""
	employee = frappe.qb.DocType("Employee")
	(
		frappe.qb.from_(employee)
		.select(employee.name)
		.where(employee.name.isin(employee_names))
		.orderby(employee.name)
		.for_update()
	).run()


def _validate_date_range(from_date, to_date):
	from_date, to_date = getdate(from_date), getdate(to_date)
	if from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date."))
	if (to_date - from_date).days + 1 > MAX_MANUAL_GENERATION_DAYS:
		frappe.throw(
			_("A single generation request cannot exceed {0} days.").format(MAX_MANUAL_GENERATION_DAYS)
		)
	return from_date, to_date


def _date_range(from_date, to_date):
	current_date = getdate(from_date)
	to_date = getdate(to_date)
	while current_date <= to_date:
		yield current_date
		current_date += timedelta(days=1)


def _require_shift_generation_role():
	frappe.only_for(("HR Manager", "System Manager"))


def _empty_result(message):
	return {
		"preview": True,
		"counts": {},
		"rows": [],
		"rows_truncated": False,
		"data_changed": False,
		"diagnostics": {"legacy_fallback_employees": 0},
		"message": message,
	}
