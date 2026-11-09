"""Read-only preview and guarded execution for backdated Shift Group transfers."""

from __future__ import annotations

import calendar
import json
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from uuid import uuid4

import frappe
from frappe.utils import cint, getdate, now_datetime, today

from vinatex.vnt_hr.attendance_processing import (
	process_attendance,
	sync_checkin_shift_fields_for_date,
)
from vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm import (
	make_attendance_confirm,
)

from vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_policy import (
	build_backdated_employee_plan,
	make_preview_token,
)
from vinatex.vnt_hr.shift_management.constants import (
	BACKDATED_TRANSFER_CONFIRMATION,
	MAX_BACKDATED_TRANSFER_EMPLOYEES,
	MAX_MANUAL_GENERATION_DAYS,
)
from vinatex.vnt_hr.shift_management.current_shift_group_sync import (
	sync_employee_current_shift_groups,
)
from vinatex.vnt_hr.shift_management.shift_assignment_service import (
	_lock_employee_rows,
	generate_shift_assignments,
)


BACKDATED_TRANSFER_ROLES = frozenset({"HR Manager", "System Manager"})


@frappe.whitelist()
def preview_backdated_shift_group_transfer(
	employees,
	target_shift_group,
	effective_date,
	membership_end_date,
	generate_until=None,
	note=None,
) -> dict:
	"""Return a tokenized, all-or-nothing preview without changing business data."""
	_require_backdated_transfer_role()
	request = _normalize_backdated_request(
		employees,
		target_shift_group,
		effective_date,
		membership_end_date,
		generate_until,
		note,
	)
	snapshots = _load_batch_snapshots(request)
	rows = [
		build_backdated_employee_plan(snapshots[employee], request)
		for employee in request["employees"]
	]
	counts = Counter(row["status"] for row in rows)
	completed_through = min(
		request["generate_until"],
		request["membership_end_date"],
		request["today"] - timedelta(days=1),
	)
	batch_status = "BLOCKED" if counts.get("BLOCKED") else "READY"
	return {
		"mode": "BACKDATED",
		"batch_status": batch_status,
		"can_execute": batch_status == "READY" and bool(rows),
		"preview_token": make_preview_token(
			{"employees": [snapshots[name] for name in request["employees"]]},
			request,
		),
		"completed_through": completed_through.isoformat(),
		"counts": dict(sorted(counts.items())),
		"action_counts": {
			"attendance": sum(len(row["attendance_actions"]) for row in rows),
			"assignments": sum(len(row["assignment_actions"]) for row in rows),
			"preserved_checkins": sum(len(row["preserved_checkins"]) for row in rows),
		},
		"rows": rows,
	}


@frappe.whitelist()
def execute_backdated_shift_group_transfer(
	employees,
	target_shift_group,
	effective_date,
	membership_end_date,
	generate_until=None,
	note=None,
	preview_token=None,
	confirmation_text=None,
) -> dict:
	"""Execute only the exact all-ready snapshot that HR previously previewed."""
	_require_backdated_transfer_role()
	if confirmation_text != BACKDATED_TRANSFER_CONFIRMATION:
		raise frappe.ValidationError(
			f"Enter exactly {BACKDATED_TRANSFER_CONFIRMATION} to execute this backdated transfer."
		)
	request = _normalize_backdated_request(
		employees,
		target_shift_group,
		effective_date,
		membership_end_date,
		generate_until,
		note,
	)
	_lock_employee_rows(request["employees"])
	_lock_backdated_dependencies(request)
	snapshots = _load_batch_snapshots(request)
	plans = [
		build_backdated_employee_plan(snapshots[employee], request)
		for employee in request["employees"]
	]
	blocked = [plan for plan in plans if plan["status"] == "BLOCKED"]
	if blocked:
		details = "; ".join(
			f"{plan['employee']}: {', '.join(row['code'] for row in plan['blockers'])}"
			for plan in blocked
		)
		raise frappe.ValidationError(f"Backdated transfer is blocked: {details}")
	current_token = make_preview_token(
		{"employees": [snapshots[name] for name in request["employees"]]},
		request,
	)
	if not preview_token or preview_token != current_token:
		raise frappe.ValidationError(
			"The backdated transfer preview is stale. Preview again before executing."
		)
	if _batch_is_already_applied(snapshots, plans, request):
		return {
			"status": "ALREADY_APPLIED",
			"operation_id": None,
			"employees": len(plans),
			"counts": {},
		}

	operation_id = str(uuid4())
	counts = Counter()
	with _execution_transaction():
		for plan in plans:
			result = _apply_employee_reconciliation(
				snapshots[plan["employee"]],
				plan,
				request,
				operation_id,
			)
			counts.update(result or {})
	return {
		"status": "COMPLETED",
		"operation_id": operation_id,
		"employees": len(plans),
		"counts": dict(sorted(counts.items())),
	}


@contextmanager
def _execution_transaction():
	"""Rollback the complete batch to its savepoint when any Employee fails."""
	savepoint = "vnt_backdated_shift_transfer"
	frappe.db.savepoint(savepoint)
	try:
		yield
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise


def _batch_is_already_applied(snapshots, plans, request):
	for plan in plans:
		if plan["membership_action"]["action"] != "ALREADY_TARGET":
			return False
		snapshot = snapshots[plan["employee"]]
		employee = snapshot.get("employee") or {}
		if employee.get("custom_shift_group") != request["target_shift_group"]:
			return False
		if employee.get("custom_working_schedule_type") != "Theo kíp":
			return False
		if not _has_matching_completion_audit(snapshot, request):
			return False
		assignments = {
			row.get("name"): row for row in snapshot.get("assignments") or []
		}
		attendances = {
			row.get("name"): row for row in snapshot.get("attendances") or []
		}
		for action in plan["assignment_actions"]:
			if action["action"] in {
				"CREATE_HISTORICAL_AUTO",
				"GENERATE_TARGET_AUTO",
				"CANCEL_HISTORICAL_AUTO",
				"CANCEL_CURRENT_AUTO",
			}:
				return False
			assignment = assignments.get(action.get("assignment"))
			if not assignment:
				return False
			if assignment.get("custom_shift_group") != request["target_shift_group"]:
				return False
			if action.get("target_shift_type") and assignment.get("shift_type") != action["target_shift_type"]:
				return False
		for action in plan["attendance_actions"]:
			if action["action"] != "CANCEL_REBUILD" or not action.get("attendance"):
				return False
			attendance = attendances.get(action["attendance"])
			if not attendance or not cint(
				attendance.get("custom_vnt_generated_by_pipeline")
			):
				return False
			source_assignment = assignments.get(
				attendance.get("custom_vnt_source_shift_assignment")
			)
			if not source_assignment:
				return False
			if (
				source_assignment.get("custom_shift_group")
				!= request["target_shift_group"]
				or source_assignment.get("shift_type") != action.get("target_shift_type")
				or attendance.get("shift") != action.get("target_shift_type")
			):
				return False
	return True


def _has_matching_completion_audit(snapshot, request):
	expected = {
		"employees": request["employees"],
		"target_shift_group": request["target_shift_group"],
		"effective_date": str(request["effective_date"]),
		"membership_end_date": str(request["membership_end_date"]),
		"generate_until": str(request["generate_until"]),
		"note": request["note"],
		"today": str(request["today"]),
	}
	for row in snapshot.get("operation_audits") or []:
		content = str(row.get("content") or "").strip()
		if content.startswith("<pre>") and content.endswith("</pre>"):
			content = content[5:-6]
		try:
			payload = json.loads(content)
		except (TypeError, ValueError):
			continue
		if (
			payload.get("summary") == "Backdated Shift Group transfer completed"
			and ((payload.get("before") or {}).get("request") or {}) == expected
		):
			return True
	return False


def _apply_employee_reconciliation(snapshot, plan, request, operation_id):
	"""Apply one Employee action plan inside the caller's batch transaction."""
	employee = plan["employee"]
	counts = Counter()

	for action in plan["attendance_actions"]:
		attendance_name = action.get("attendance")
		if not attendance_name:
			continue
		attendance = frappe.get_doc("Attendance", attendance_name)
		if (
			attendance.employee != employee
			or getdate(attendance.attendance_date) != getdate(action["work_date"])
			or cint(attendance.docstatus) >= 2
		):
			raise frappe.ValidationError(
				f"Attendance {attendance_name} no longer matches the approved action plan."
			)
		attendance.flags.ignore_permissions = True
		attendance.cancel()
		counts["attendance_cancelled"] += 1

	for action in plan["assignment_actions"]:
		assignment_name = action.get("assignment")
		if not assignment_name:
			continue
		assignment = frappe.get_doc("Shift Assignment", assignment_name)
		_validate_exact_assignment(assignment, action, employee)
		if action["action"] == "REWRITE_HISTORICAL_AUTO":
			_rewrite_historical_auto_assignment(assignment, action, operation_id)
			counts["historical_assignments_rewritten"] += 1
		elif action["action"] == "CANCEL_HISTORICAL_AUTO":
			_cancel_historical_auto_assignment(assignment, action, operation_id)
			counts["historical_assignments_cancelled"] += 1
		elif action["action"] == "REWRITE_CURRENT_AUTO":
			_rewrite_historical_auto_assignment(
				assignment,
				action,
				operation_id,
				summary="Current-day automatic assignment rewritten",
			)
			counts["current_assignments_rewritten"] += 1
		elif action["action"] == "CANCEL_CURRENT_AUTO":
			_cancel_historical_auto_assignment(
				assignment,
				action,
				operation_id,
				summary="Current-day automatic assignment cancelled for target OFF day",
			)
			counts["current_assignments_cancelled"] += 1
		elif action["action"] == "CANCEL_UNUSED_AUTO":
			_cancel_unused_auto_assignment(assignment, action, operation_id)
			counts["unused_assignments_cancelled"] += 1

	counts.update(_apply_membership_action(snapshot, plan, request, operation_id))
	sync_result = sync_employee_current_shift_groups(
		[employee],
		request["today"],
	)
	for status, value in (sync_result.get("counts") or {}).items():
		counts[f"employee_cache_{status.lower()}"] += cint(value)
	counts["employees_updated"] += cint(
		(sync_result.get("counts") or {}).get("UPDATED")
	)

	generation = generate_shift_assignments(
		request["effective_date"],
		request["generate_until"],
		employees=[employee],
		shift_group=request["target_shift_group"],
		preview=False,
	)
	if cint((generation.get("counts") or {}).get("ERROR")):
		raise frappe.ValidationError(
			f"Shift generation failed for {employee}; the batch will be rolled back."
		)
	counts["assignments_generated"] += cint(
		(generation.get("counts") or {}).get("CREATE")
	)

	counts["current_day_checkins_resynced"] += cint(
		sync_checkin_shift_fields_for_date(request["today"], [employee])
	)

	completed_through = getdate(plan["completed_through"])
	if request["effective_date"] <= completed_through:
		attendance_result = process_attendance(
			request["effective_date"],
			completed_through,
			employee_names=[employee],
		)
		if cint(attendance_result.get("Số lỗi")):
			raise frappe.ValidationError(
				f"Attendance processing failed for {employee}; the batch will be rolled back."
			)
		counts["attendance_created"] += cint(
			attendance_result.get("Số Attendance tạo mới")
		)
		counts["attendance_repaired"] += cint(
			attendance_result.get("Số Attendance bổ sung giờ vào/ra")
		)
		counts["confirmation_months_refreshed"] += _refresh_attendance_confirmations(
			employee,
			request["effective_date"],
			completed_through,
		)

	_add_audit_comment(
		"Employee",
		employee,
		operation_id,
		"Backdated Shift Group transfer completed",
		before={
			"custom_shift_group": (snapshot.get("employee") or {}).get("custom_shift_group"),
			"custom_working_schedule_type": (snapshot.get("employee") or {}).get(
				"custom_working_schedule_type"
			),
			"request": request,
		},
	)
	return dict(counts)


def _rewrite_historical_auto_assignment(
	assignment,
	action,
	operation_id,
	*,
	summary="Historical automatic assignment rewritten",
) -> None:
	_assert_engine_assignment(assignment)
	before = _assignment_before_snapshot(assignment)
	_add_audit_comment(
		"Shift Assignment",
		assignment.name,
		operation_id,
		summary,
		before=before,
	)
	frappe.db.set_value(
		"Shift Assignment",
		assignment.name,
		{
			"shift_type": action["target_shift_type"],
			"custom_shift_group": action["target_shift_group"],
			"custom_schedule_date": getdate(action["work_date"]),
			"status": "Active",
		},
	)


def _cancel_historical_auto_assignment(
	assignment,
	action,
	operation_id,
	*,
	summary="Historical automatic assignment cancelled for target OFF day",
) -> None:
	_assert_engine_assignment(assignment)
	work_date = getdate(action["work_date"])
	if frappe.db.count(
		"Attendance",
		filters={
			"employee": assignment.employee,
			"attendance_date": work_date,
			"docstatus": ["<", 2],
		},
	):
		raise frappe.ValidationError(
			f"Active Attendance still exists for {assignment.employee} on {work_date}."
		)
	if frappe.db.count(
		"Employee Checkin",
		filters={
			"employee": assignment.employee,
			"shift_start": [
				"between",
				[
					datetime.combine(work_date, time.min),
					datetime.combine(work_date, time.max),
				],
			],
			"attendance": ["is", "set"],
			"docstatus": ["<", 2],
		},
	):
		raise frappe.ValidationError(
			f"Linked Checkin still exists for {assignment.employee} on {work_date}."
		)
	_add_audit_comment(
		"Shift Assignment",
		assignment.name,
		operation_id,
		summary,
		before=_assignment_before_snapshot(assignment),
	)
	frappe.db.set_value(
		"Shift Assignment",
		assignment.name,
		{
			"docstatus": 2,
			"status": "Inactive",
			"modified": now_datetime(),
			"modified_by": _current_user(),
		},
		update_modified=False,
	)


def _cancel_unused_auto_assignment(assignment, action, operation_id):
	_assert_engine_assignment(assignment)
	_add_audit_comment(
		"Shift Assignment",
		assignment.name,
		operation_id,
		"Unused automatic assignment cancelled before regeneration",
		before=_assignment_before_snapshot(assignment),
	)
	assignment.flags.ignore_permissions = True
	assignment.cancel()


def _validate_exact_assignment(assignment, action, employee):
	_assert_engine_assignment(assignment)
	work_date = getdate(action["work_date"])
	if (
		assignment.employee != employee
		or getdate(assignment.start_date) != work_date
		or getdate(assignment.end_date or assignment.start_date) != work_date
		or cint(assignment.docstatus) >= 2
	):
		raise frappe.ValidationError(
			f"Shift Assignment {assignment.name} no longer matches its exact daily action."
		)


def _assert_engine_assignment(assignment):
	if not (
		cint(assignment.get("custom_generated_by_shift_group"))
		and assignment.get("custom_assignment_source") == "Kíp tự động"
	):
		raise frappe.ValidationError(
			f"Shift Assignment {assignment.name} is not an engine-generated assignment."
		)


def _assignment_before_snapshot(assignment):
	return {
		fieldname: assignment.get(fieldname)
		for fieldname in (
			"name",
			"employee",
			"shift_type",
			"start_date",
			"end_date",
			"status",
			"docstatus",
			"custom_assignment_source",
			"custom_shift_group",
			"custom_generated_by_shift_group",
			"custom_schedule_date",
		)
	}


def _apply_membership_action(snapshot, plan, request, operation_id):
	action = plan["membership_action"]
	if action["action"] == "ALREADY_TARGET":
		return {}
	counts = Counter()
	if action["action"] == "EXTEND_TARGET":
		membership = frappe.get_doc(
			"VNT Shift Group Assignment", action["source_membership"]
		)
		if membership.shift_group != request["target_shift_group"]:
			raise frappe.ValidationError(
				f"Membership {membership.name} no longer matches the preview."
			)
		membership.to_date = request["membership_end_date"]
		membership.note = _append_audit_note(
			membership.note, operation_id, request["note"]
		)
		membership.save(ignore_permissions=True)
		counts["memberships_extended"] += 1
		return dict(counts)
	if action.get("source_membership"):
		membership = frappe.get_doc(
			"VNT Shift Group Assignment", action["source_membership"]
		)
		if membership.shift_group != action.get("source_shift_group"):
			raise frappe.ValidationError(
				f"Membership {membership.name} no longer matches the preview."
			)
		if action["action"] == "INACTIVATE_SOURCE_CREATE_TARGET":
			membership.status = "Inactive"
			counts["memberships_inactivated"] += 1
		else:
			membership.to_date = getdate(action["source_end_date"])
			counts["memberships_closed"] += 1
		membership.note = _append_audit_note(membership.note, operation_id, request["note"])
		membership.save(ignore_permissions=True)

	employee = snapshot.get("employee") or {}
	membership = frappe.get_doc(
		{
			"doctype": "VNT Shift Group Assignment",
			"employee": plan["employee"],
			"employee_name": plan.get("employee_name") or employee.get("employee_name"),
			"company": employee.get("company"),
			"shift_group": request["target_shift_group"],
			"from_date": request["effective_date"],
			"to_date": request["membership_end_date"],
			"status": "Active",
			"note": _append_audit_note(None, operation_id, request["note"]),
		}
	)
	membership.insert(ignore_permissions=True)
	counts["memberships_created"] += 1
	return dict(counts)


def _append_audit_note(existing, operation_id, note):
	audit = f"[{operation_id}] {note}"
	return f"{existing}\n{audit}" if existing else audit


def _refresh_attendance_confirmations(employee, from_date, to_date):
	from_date, to_date = getdate(from_date), getdate(to_date)
	if from_date > to_date:
		return 0
	count = 0
	cursor = from_date.replace(day=1)
	while cursor <= to_date:
		month_end = date(
			cursor.year,
			cursor.month,
			calendar.monthrange(cursor.year, cursor.month)[1],
		)
		chunk_end = min(month_end, to_date)
		make_attendance_confirm(
			from_date=cursor,
			to_date=chunk_end,
			employee=employee,
		)
		count += 1
		cursor = chunk_end + timedelta(days=1)
	return count


def _lock_backdated_dependencies(request):
	"""Lock the exact source ranges whose eligibility is revalidated below."""
	employees = request["employees"]
	effective_date = request["effective_date"]
	end_date = request["membership_end_date"]
	checkin_end = datetime.combine(request["today"] + timedelta(days=1), time.min)

	def lock(query, order_field, *, as_dict=False):
		return query.orderby(order_field).for_update().run(as_dict=as_dict)

	group = frappe.qb.DocType("VNT Shift Group")
	group_rows = lock(
		frappe.qb.from_(group)
		.select(group.name, group.holiday_list)
		.where(group.name == request["target_shift_group"]),
		group.name,
		as_dict=True,
	)
	schedule = frappe.qb.DocType("VNT Shift Group Schedule")
	schedule_rows = lock(
		frappe.qb.from_(schedule)
		.select(schedule.name, schedule.shift_type)
		.where(schedule.parent == request["target_shift_group"])
		,
		schedule.name,
		as_dict=True,
	)
	employee = frappe.qb.DocType("Employee")
	employee_rows = lock(
		frappe.qb.from_(employee)
		.select(employee.name, employee.company, employee.holiday_list, employee.default_shift)
		.where(employee.name.isin(employees)),
		employee.name,
		as_dict=True,
	)
	shift_names = sorted(
		{
			row.shift_type
			for row in schedule_rows
			if row.get("shift_type")
		}
		| {row.default_shift for row in employee_rows if row.get("default_shift")}
	)
	shift_rows = []
	if shift_names:
		shift_type = frappe.qb.DocType("Shift Type")
		shift_rows = lock(
			frappe.qb.from_(shift_type)
			.select(shift_type.name, shift_type.holiday_list)
			.where(shift_type.name.isin(shift_names)),
			shift_type.name,
			as_dict=True,
		)
	company_names = sorted({row.company for row in employee_rows if row.get("company")})
	company_rows = []
	if company_names:
		company = frappe.qb.DocType("Company")
		company_rows = lock(
			frappe.qb.from_(company)
			.select(company.name, company.default_holiday_list)
			.where(company.name.isin(company_names)),
			company.name,
			as_dict=True,
		)
	holiday_lists = {
		*(row.get("holiday_list") for row in group_rows),
		*(row.get("holiday_list") for row in employee_rows),
		*(row.get("holiday_list") for row in shift_rows),
		*(row.get("default_holiday_list") for row in company_rows),
	}
	holiday_lists.discard(None)
	holiday_lists.discard("")
	if holiday_lists:
		holiday = frappe.qb.DocType("Holiday")
		lock(
			frappe.qb.from_(holiday)
			.select(holiday.name)
			.where(
				holiday.parent.isin(sorted(holiday_lists))
				& (holiday.holiday_date >= effective_date - timedelta(days=1))
				& (holiday.holiday_date <= request["today"])
			),
			holiday.name,
		)

	queries = []
	membership = frappe.qb.DocType("VNT Shift Group Assignment")
	queries.append((
		frappe.qb.from_(membership)
		.select(membership.name)
		.where(
			membership.employee.isin(employees)
			& (membership.from_date <= end_date)
			& ((membership.to_date >= effective_date) | membership.to_date.isnull())
		), membership.name))
	assignment = frappe.qb.DocType("Shift Assignment")
	queries.append((
		frappe.qb.from_(assignment)
		.select(assignment.name)
		.where(
			assignment.employee.isin(employees)
			& (assignment.start_date <= request["generate_until"])
			& ((assignment.end_date >= effective_date) | assignment.end_date.isnull())
			& (assignment.docstatus < 2)
		), assignment.name))
	attendance = frappe.qb.DocType("Attendance")
	queries.append((
		frappe.qb.from_(attendance)
		.select(attendance.name)
		.where(
			attendance.employee.isin(employees)
			& (attendance.attendance_date >= effective_date - timedelta(days=1))
			& (attendance.attendance_date <= request["today"])
			& (attendance.docstatus < 2)
		), attendance.name))
	checkin = frappe.qb.DocType("Employee Checkin")
	queries.append((
		frappe.qb.from_(checkin)
		.select(checkin.name)
		.where(
			checkin.employee.isin(employees)
			& (checkin.time >= datetime.combine(effective_date, time.min))
			& (checkin.time < checkin_end)
			& (checkin.docstatus < 2)
		), checkin.name))
	salary_slip = frappe.qb.DocType("Salary Slip")
	queries.append((
		frappe.qb.from_(salary_slip)
		.select(salary_slip.name)
		.where(
			salary_slip.employee.isin(employees)
			& (salary_slip.start_date <= end_date)
			& (salary_slip.end_date >= effective_date)
			& (salary_slip.docstatus == 1)
		), salary_slip.name))
	for query, order_field in queries:
		lock(query, order_field)

	confirmation = frappe.qb.DocType("VNT Attendance Confirm")
	confirmation_rows = lock(
		frappe.qb.from_(confirmation)
		.select(confirmation.name)
		.where(
			confirmation.employee.isin(employees)
			& (confirmation.from_date <= end_date)
			& (confirmation.to_date >= effective_date)
			& (confirmation.docstatus < 2)
		),
		confirmation.name,
		as_dict=True,
	)
	confirmation_names = [row.name for row in confirmation_rows]
	if confirmation_names:
		confirmation_item = frappe.qb.DocType("VNT Attendance Confirm Item")
		lock(
			frappe.qb.from_(confirmation_item)
			.select(confirmation_item.name)
			.where(confirmation_item.parent.isin(confirmation_names)),
			confirmation_item.name,
		)
	comment = frappe.qb.DocType("Comment")
	lock(
		frappe.qb.from_(comment)
		.select(comment.name)
		.where(
			(comment.reference_doctype == "Employee")
			& comment.reference_name.isin(employees)
			& (comment.comment_type == "Info")
		),
		comment.name,
	)


def _add_audit_comment(reference_doctype, reference_name, operation_id, summary, *, before=None):
	payload = {
		"operation_id": operation_id,
		"summary": summary,
		"before": before,
	}
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"content": f"<pre>{json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True)}</pre>",
		}
	).insert(ignore_permissions=True)


def _current_user():
	try:
		return frappe.session.user
	except (AttributeError, RuntimeError):
		return "Administrator"


def _normalize_backdated_request(
	employees,
	target_shift_group,
	effective_date,
	membership_end_date,
	generate_until=None,
	note=None,
) -> dict:
	if isinstance(employees, str):
		employees = frappe.parse_json(employees)
	if not isinstance(employees, (list, tuple)):
		raise frappe.ValidationError("Employees must be a list.")
	employee_names = []
	for row in employees:
		value = (row.get("name") or row.get("employee")) if isinstance(row, dict) else row
		if value:
			employee_names.append(str(value))
	employee_names = sorted(set(employee_names))
	if not employee_names:
		raise frappe.ValidationError("Select at least one Employee.")
	if len(employee_names) > MAX_BACKDATED_TRANSFER_EMPLOYEES:
		raise frappe.ValidationError(
			f"A backdated transfer cannot exceed {MAX_BACKDATED_TRANSFER_EMPLOYEES} Employees."
		)

	effective_date = getdate(effective_date)
	membership_end_date = getdate(membership_end_date)
	generate_until = getdate(generate_until or membership_end_date)
	current_date = getdate(today())
	if effective_date >= current_date:
		raise frappe.ValidationError("Backdated Effective Date must be before today.")
	if membership_end_date < current_date:
		raise frappe.ValidationError("Membership End Date cannot be before today.")
	if effective_date > membership_end_date:
		raise frappe.ValidationError("Effective Date cannot be after Membership End Date.")
	if not (effective_date <= generate_until <= membership_end_date):
		raise frappe.ValidationError("Generate Until must be inside the membership period.")
	if (membership_end_date - effective_date).days + 1 > MAX_MANUAL_GENERATION_DAYS:
		raise frappe.ValidationError(
			f"Backdated period cannot exceed {MAX_MANUAL_GENERATION_DAYS} days."
		)
	if not str(note or "").strip():
		raise frappe.ValidationError("Reason/Note is required for audit.")
	return {
		"employees": employee_names,
		"target_shift_group": str(target_shift_group or "").strip(),
		"effective_date": effective_date,
		"membership_end_date": membership_end_date,
		"generate_until": generate_until,
		"note": str(note).strip(),
		"today": current_date,
	}


def _load_batch_snapshots(request: dict) -> dict:
	"""Load one canonical snapshot per Employee using batched read queries only."""
	employee_names = request["employees"]
	_require_employee_access(employee_names)
	employee_fields = [
		"name",
		"employee_name",
		"company",
		"department",
		"designation",
		"holiday_list",
		"status",
		"default_shift",
		"modified",
		"docstatus",
	]
	employee_meta = frappe.get_meta("Employee")
	for fieldname in ("custom_shift_group", "custom_working_schedule_type"):
		if employee_meta.has_field(fieldname):
			employee_fields.append(fieldname)
	employees = frappe.get_all(
		"Employee",
		filters={"name": ["in", employee_names]},
		fields=employee_fields,
		order_by="name asc",
	)
	by_name = {row.name: row for row in employees}
	missing = sorted(set(employee_names) - set(by_name))
	if missing:
		raise frappe.ValidationError(f"Employee not found: {', '.join(missing)}")

	groups = frappe.get_all(
		"VNT Shift Group",
		filters={"name": request["target_shift_group"]},
		fields=[
			"name",
			"company",
			"disabled",
			"effective_from",
			"effective_to",
			"holiday_list",
			"modified",
			"docstatus",
		],
		limit=1,
	)
	if not groups:
		raise frappe.ValidationError("Target Shift Group does not exist.")
	target_group = groups[0]

	schedules = frappe.get_all(
		"VNT Shift Group Schedule",
		filters={"parent": target_group.name, "parenttype": "VNT Shift Group"},
		fields=[
			"name",
			"parent as shift_group",
			"day_of_week as weekday",
			"shift_type",
			"is_off",
			"sequence",
			"modified",
			"docstatus",
		],
		order_by="idx asc",
	)
	shift_type_names = sorted(
		{row.shift_type for row in schedules if row.shift_type}
		| {row.default_shift for row in employees if row.default_shift}
	)
	shift_types = (
		frappe.get_all(
			"Shift Type",
			filters={"name": ["in", shift_type_names]},
			fields=[
				"name",
				"start_time",
				"end_time",
				"determine_check_in_and_check_out",
				"working_hours_calculation_based_on",
				"begin_check_in_before_shift_start_time",
				"allow_check_out_after_shift_end_time",
				"enable_late_entry_marking",
				"late_entry_grace_period",
				"enable_early_exit_marking",
				"early_exit_grace_period",
				"working_hours_threshold_for_half_day",
				"working_hours_threshold_for_absent",
				"holiday_list",
				"modified",
				"docstatus",
			],
			order_by="name asc",
		)
		if shift_type_names
		else []
	)

	memberships = frappe.get_all(
		"VNT Shift Group Assignment",
		filters={
			"employee": ["in", employee_names],
			"status": "Active",
			"from_date": ["<=", request["membership_end_date"]],
		},
		or_filters=[
			["to_date", ">=", request["effective_date"]],
			["to_date", "is", "not set"],
		],
		fields=[
			"name",
			"employee",
			"employee_name",
			"shift_group",
			"company",
			"from_date",
			"to_date",
			"status",
			"note",
			"modified",
			"docstatus",
		],
		order_by="employee asc, from_date asc, name asc",
	)
	assignment_fields = [
		"name",
		"employee",
		"start_date",
		"end_date",
		"shift_type",
		"status",
		"modified",
		"docstatus",
	]
	assignment_meta = frappe.get_meta("Shift Assignment")
	for fieldname in (
		"custom_assignment_source",
		"custom_shift_group",
		"custom_generated_by_shift_group",
		"custom_schedule_date",
	):
		if assignment_meta.has_field(fieldname):
			assignment_fields.append(fieldname)
	assignments = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": ["in", employee_names],
			"start_date": ["<=", request["generate_until"]],
			"docstatus": ["<", 2],
		},
		or_filters=[
			["end_date", ">=", request["effective_date"]],
			["end_date", "is", "not set"],
		],
		fields=assignment_fields,
		order_by="employee asc, start_date asc, name asc",
	)

	attendance_fields = [
		"name",
		"employee",
		"attendance_date",
		"shift",
		"status",
		"leave_type",
		"in_time",
		"out_time",
		"working_hours",
		"modified",
		"docstatus",
	]
	attendance_meta = frappe.get_meta("Attendance")
	for fieldname in (
		"leave_application",
		"attendance_request",
		"custom_vnt_generated_by_pipeline",
		"custom_vnt_source_shift_assignment",
	):
		if attendance_meta.has_field(fieldname):
			attendance_fields.append(fieldname)
	attendances = frappe.get_all(
		"Attendance",
		filters={
			"employee": ["in", employee_names],
			"attendance_date": [
				"between",
				[request["effective_date"] - timedelta(days=1), request["today"]],
			],
			"docstatus": ["<", 2],
		},
		fields=attendance_fields,
		order_by="employee asc, attendance_date asc, name asc",
	)
	checkins = frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": ["in", employee_names],
			"time": [
				"between",
				[
					datetime.combine(request["effective_date"], time.min),
					datetime.combine(request["today"] + timedelta(days=1), time.min),
				],
			],
			"docstatus": ["<", 2],
		},
		fields=[
			"name",
			"employee",
			"time",
			"log_type",
			"attendance",
			"shift",
			"shift_start",
			"shift_end",
			"offshift",
			"skip_auto_attendance",
			"modified",
			"docstatus",
		],
		order_by="employee asc, time asc, name asc",
	)
	company_names = sorted({row.company for row in employees if row.company})
	companies = (
		frappe.get_all(
			"Company",
			filters={"name": ["in", company_names]},
			fields=["name", "default_holiday_list", "modified", "docstatus"],
			order_by="name asc",
		)
		if company_names
		else []
	)
	holiday_lists = {
		target_group.holiday_list,
		*(row.get("holiday_list") for row in employees),
		*(row.get("default_holiday_list") for row in companies),
		*(row.get("holiday_list") for row in shift_types),
	}
	holiday_lists.discard(None)
	holiday_lists.discard("")
	holidays = (
		frappe.get_all(
			"Holiday",
			filters={
				"parent": ["in", sorted(holiday_lists)],
				"holiday_date": [
					"between",
					[request["effective_date"] - timedelta(days=1), request["today"]],
				],
			},
			fields=[
				"name",
				"parent",
				"holiday_date",
				"weekly_off",
				"description",
				"modified",
				"docstatus",
			],
			order_by="parent asc, holiday_date asc, name asc",
		)
		if holiday_lists
		else []
	)

	completed_through = min(
		request["generate_until"],
		request["membership_end_date"],
		request["today"] - timedelta(days=1),
	)
	confirm_parents = frappe.get_all(
		"VNT Attendance Confirm",
		filters={
			"employee": ["in", employee_names],
			"from_date": ["<=", completed_through],
			"to_date": [">=", request["effective_date"]],
		},
		fields=["name", "employee", "status", "modified", "docstatus"],
		order_by="employee asc, name asc",
	)
	confirm_parent_employee = {row.name: row.employee for row in confirm_parents}
	confirmation_rows = []
	if confirm_parent_employee:
		confirmation_rows = frappe.get_all(
			"VNT Attendance Confirm Item",
			filters={
				"parent": ["in", sorted(confirm_parent_employee)],
				"date": ["between", [request["effective_date"], completed_through]],
			},
			fields=[
				"name",
				"parent",
				"date as work_date",
				"confirm as hr_result",
				"type",
				"reviewed_by",
				"reviewed_on",
				"modified",
				"docstatus",
			],
			order_by="parent asc, date asc, name asc",
		)
	for row in confirmation_rows:
		row.employee = confirm_parent_employee.get(row.parent)

	salary_slips = frappe.get_all(
		"Salary Slip",
		filters={
			"employee": ["in", employee_names],
			"start_date": ["<=", completed_through],
			"end_date": [">=", request["effective_date"]],
			"docstatus": 1,
		},
		fields=["name", "employee", "start_date", "end_date", "modified", "docstatus"],
		order_by="employee asc, start_date asc, name asc",
	)
	operation_audits = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "Employee",
			"reference_name": ["in", employee_names],
			"comment_type": "Info",
			"content": ["like", "%Backdated Shift Group transfer completed%"],
		},
		fields=[
			"name",
			"reference_name as employee",
			"content",
			"creation",
			"modified",
			"owner",
		],
		order_by="reference_name asc, creation asc, name asc",
	)

	collections = {
		"memberships": _group_by_employee(memberships),
		"assignments": _group_by_employee(assignments),
		"attendances": _group_by_employee(attendances),
		"checkins": _group_by_employee(checkins),
		"confirmations": _group_by_employee(confirmation_rows),
		"salary_slips": _group_by_employee(salary_slips),
		"operation_audits": _group_by_employee(operation_audits),
	}
	return {
		employee: {
			"employee": dict(by_name[employee]),
			"target_group": dict(target_group),
			"schedules": [dict(row) for row in schedules],
			"shift_types": [dict(row) for row in shift_types],
			"companies": [dict(row) for row in companies],
			"holidays": [dict(row) for row in holidays],
			**{
				key: [dict(row) for row in rows.get(employee, [])]
				for key, rows in collections.items()
			},
		}
		for employee in employee_names
	}


def _group_by_employee(rows):
	result = defaultdict(list)
	for row in rows:
		result[row.employee].append(row)
	return result


def _get_current_roles():
	return set(frappe.get_roles(frappe.session.user))


def _require_backdated_transfer_role():
	if not BACKDATED_TRANSFER_ROLES.intersection(_get_current_roles()):
		raise frappe.PermissionError(
			"Only HR Manager or System Manager can perform a backdated Shift Group transfer."
		)


def _require_employee_access(employee_names):
	denied = [
		employee
		for employee in employee_names
		if not frappe.has_permission("Employee", "read", doc=employee)
	]
	if denied:
		raise frappe.PermissionError(
			f"Not permitted to transfer Employees: {', '.join(denied[:10])}"
		)
