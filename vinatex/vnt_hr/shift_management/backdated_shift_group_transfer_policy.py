"""Pure planning rules for guarded, backdated Shift Group transfers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from vinatex.vnt_hr.attendance_processing import select_checkin_window

from vinatex.vnt_hr.shift_management.constants import (
	AUTO_ASSIGNMENT_SOURCE,
	MAX_BACKDATED_TRANSFER_EMPLOYEES,
	MAX_MANUAL_GENERATION_DAYS,
	SUNDAY_WORKDAY_DEPARTMENTS,
	SUNDAY_WORKDAY_SHIFT_GROUP,
)


def build_backdated_employee_plan(snapshot: dict, request: dict) -> dict:
	"""Return a deterministic action plan without reading or writing Frappe state."""
	request = _normalize_request(request)
	employee = snapshot.get("employee") or {}
	employee_name = _value(employee, "name")
	blockers = []

	def block(code, message, *, references=None):
		if code not in {row["code"] for row in blockers}:
			blockers.append(
				{
					"code": code,
					"message": message,
					"references": sorted(str(value) for value in (references or [])),
				}
			)

	_validate_request_for_employee(request, block)
	_validate_employee_and_group(snapshot, request, block)

	effective_date = request["effective_date"]
	membership_end_date = request["membership_end_date"]
	completed_through = min(
		request["generate_until"],
		membership_end_date,
		request["today"] - timedelta(days=1),
	)

	membership_action = _plan_membership(snapshot, request, block)
	schedules = {_value(row, "weekday"): row for row in snapshot.get("schedules") or []}
	shift_types = {_value(row, "name"): row for row in snapshot.get("shift_types") or []}
	assignments = snapshot.get("assignments") or []
	assignments_by_date = _assignments_by_date(
		assignments,
		effective_date,
		request["generate_until"],
	)
	attendance_by_date = {}
	for row in snapshot.get("attendances") or []:
		if _value(row, "attendance_date") and int(_value(row, "docstatus", 0) or 0) < 2:
			attendance_by_date.setdefault(
				_to_date(_value(row, "attendance_date")), []
			).append(row)
	attendance_by_name = {
		_value(row, "name"): row
		for row in snapshot.get("attendances") or []
		if _value(row, "name")
	}
	checkins = [
		row
		for row in snapshot.get("checkins") or []
		if int(_value(row, "docstatus", 0) or 0) < 2
	]
	checkins_by_attendance = {}
	for row in checkins:
		if _value(row, "attendance"):
			checkins_by_attendance.setdefault(_value(row, "attendance"), []).append(row)

	preserved_checkins = []
	for row in checkins:
		linked_attendance = attendance_by_name.get(_value(row, "attendance"))
		if linked_attendance and _to_date(_value(linked_attendance, "attendance_date")) < effective_date:
			preserved_checkins.append(_value(row, "name"))

	_target_plan = {}
	assignment_actions = []
	attendance_actions = []
	for work_date in _date_range(effective_date, request["generate_until"]):
		schedule = schedules.get(work_date.strftime("%A"))
		if not schedule:
			block(
				"TARGET_SCHEDULE_MISSING",
				f"Target Shift Group has no schedule for {work_date:%A}.",
				references=[work_date.isoformat()],
			)
			continue
		is_off = bool(int(_value(schedule, "is_off", 0) or 0))
		target_shift_type = None if is_off else _value(schedule, "shift_type")
		if _uses_department_sunday_workday_policy(
			employee,
			request["target_shift_group"],
			work_date,
			is_off,
			shift_types,
		):
			is_off = False
			target_shift_type = _value(employee, "default_shift")
		if not is_off and (
			not target_shift_type or target_shift_type not in shift_types
		):
			block(
				"TARGET_SHIFT_TYPE_MISSING",
				"Target schedule does not resolve to a valid Shift Type.",
				references=[_value(schedule, "name"), work_date.isoformat()],
			)
		_target_plan[work_date] = {
			"is_off": is_off,
			"shift_type": target_shift_type,
			"shift_doc": shift_types.get(target_shift_type),
		}

		rows = assignments_by_date.get(work_date, [])
		if len(rows) > 1:
			block(
				"OVERLAPPING_SHIFT_ASSIGNMENTS",
				"Multiple Shift Assignments cover the same work date.",
				references=[_value(row, "name") for row in rows],
			)
		for assignment in rows:
			if not _is_engine_assignment(assignment):
				block(
					"MANUAL_SHIFT_ASSIGNMENT",
					"Manual or legacy Shift Assignment cannot be rewritten automatically.",
					references=[_value(assignment, "name")],
				)
				continue
			if (
				_value(assignment, "custom_shift_group") == request["target_shift_group"]
				and not is_off
				and _value(assignment, "shift_type") == target_shift_type
			):
				continue
			if work_date <= completed_through:
				action = "CANCEL_HISTORICAL_AUTO" if is_off else "REWRITE_HISTORICAL_AUTO"
			elif work_date == request["today"]:
				# Today's punches may already reference this row, and HRMS refuses
				# to cancel an assignment whose Shift Type a same-day punch uses.
				action = "CANCEL_CURRENT_AUTO" if is_off else "REWRITE_CURRENT_AUTO"
			else:
				action = "CANCEL_UNUSED_AUTO"
			assignment_actions.append(
				{
					"action": action,
					"assignment": _value(assignment, "name"),
					"work_date": work_date.isoformat(),
					"target_shift_type": target_shift_type,
					"target_shift_group": request["target_shift_group"],
				}
			)
		if not rows and not is_off:
			assignment_actions.append(
				{
					"action": (
						"CREATE_HISTORICAL_AUTO"
						if work_date <= completed_through
						else "GENERATE_TARGET_AUTO"
					),
					"assignment": None,
					"work_date": work_date.isoformat(),
					"target_shift_type": target_shift_type,
					"target_shift_group": request["target_shift_group"],
				}
			)

	for attendance_date, attendances in attendance_by_date.items():
		if attendance_date == request["today"]:
			block(
				"CURRENT_WORK_DATE_DATA",
				"Attendance for today's work date cannot be rebuilt.",
				references=[_value(row, "name") for row in attendances],
			)
		if not (effective_date <= attendance_date <= completed_through):
			continue
		if len(attendances) > 1:
			block(
				"MULTIPLE_ACTIVE_ATTENDANCE",
				"Multiple active Attendance records exist for the same work date.",
				references=[_value(row, "name") for row in attendances],
			)
		protected = [row for row in attendances if _attendance_has_protected_source(row)]
		if protected:
			block(
				"PROTECTED_ATTENDANCE_SOURCE",
				"Leave, Attendance Request, or protected Attendance status cannot be rebuilt.",
				references=[_value(row, "name") for row in protected],
			)
		if len(attendances) != 1 or protected:
			continue
		attendance = attendances[0]
		linked_logs = checkins_by_attendance.get(_value(attendance, "name"), [])
		if not _attendance_is_provenanced(attendance, assignments_by_date.get(attendance_date, []), linked_logs):
			block(
				"AMBIGUOUS_LEGACY_ATTENDANCE",
				"Legacy Attendance lacks linked Checkin and automatic Shift Assignment evidence.",
				references=[_value(attendance, "name")],
			)
			continue
		target = _target_plan.get(attendance_date) or {}
		attendance_actions.append(
			{
				"action": "CANCEL_FOR_TARGET_OFF" if target.get("is_off") else "CANCEL_REBUILD",
				"attendance": _value(attendance, "name"),
				"work_date": attendance_date.isoformat(),
				"target_shift_type": target.get("shift_type"),
			}
		)

	existing_action_dates = {
		_to_date(row["work_date"])
		for row in attendance_actions
	}
	for work_date in _date_range(effective_date, completed_through):
		target = _target_plan.get(work_date)
		if not target or target["is_off"] or work_date in existing_action_dates:
			continue
		attendance_actions.append(
			{
				"action": "PROCESS_WORK_DATE",
				"attendance": None,
				"work_date": work_date.isoformat(),
				"target_shift_type": target["shift_type"],
			}
		)

	preserved_checkins.extend(
		_current_day_checkins_to_preserve(
			checkins,
			attendance_by_name,
			_target_plan,
			request,
		)
	)
	_validate_confirmations(snapshot, effective_date, completed_through, block)
	_validate_salary_slips(snapshot, effective_date, completed_through, block)

	return {
		"employee": employee_name,
		"employee_name": _value(employee, "employee_name"),
		"authoritative_shift_group": membership_action.get("source_shift_group"),
		"display_shift_group": _value(employee, "custom_shift_group"),
		"display_mismatch": bool(
			membership_action.get("source_shift_group")
			and _value(employee, "custom_shift_group")
			!= membership_action.get("source_shift_group")
		),
		"status": "BLOCKED" if blockers else "READY",
		"blockers": sorted(blockers, key=lambda row: (row["code"], row["references"])),
		"attendance_actions": sorted(attendance_actions, key=lambda row: (row["work_date"], row["action"])),
		"assignment_actions": sorted(assignment_actions, key=lambda row: (row["work_date"], row["action"])),
		"membership_action": membership_action,
		"preserved_checkins": sorted(value for value in preserved_checkins if value),
		"confirmation_months": _month_keys(effective_date, completed_through),
		"completed_through": completed_through.isoformat(),
	}


def make_preview_token(snapshot: dict, request: dict) -> str:
	"""Hash every canonical request/snapshot value so stale previews cannot execute."""
	payload = {
		"request": _canonicalize(_normalize_request(request)),
		"snapshot": _canonicalize(snapshot),
	}
	encoded = json.dumps(
		payload,
		ensure_ascii=False,
		sort_keys=True,
		separators=(",", ":"),
	).encode("utf-8")
	return hashlib.sha256(encoded).hexdigest()


def _validate_request_for_employee(request, block):
	if len(request["employees"]) > MAX_BACKDATED_TRANSFER_EMPLOYEES:
		block(
			"BATCH_LIMIT_EXCEEDED",
			f"Backdated transfer cannot exceed {MAX_BACKDATED_TRANSFER_EMPLOYEES} Employees.",
		)
	if request["effective_date"] >= request["today"]:
		block("NOT_BACKDATED", "Effective Date must be before today.")
	if request["membership_end_date"] < request["today"]:
		block("MEMBERSHIP_END_BEFORE_TODAY", "Membership End Date cannot be before today.")
	if request["effective_date"] > request["membership_end_date"]:
		block("INVALID_DATE_RANGE", "Effective Date cannot be after Membership End Date.")
	if not (
		request["effective_date"]
		<= request["generate_until"]
		<= request["membership_end_date"]
	):
		block("INVALID_GENERATE_UNTIL", "Generate Until must be inside the membership period.")
	if (request["membership_end_date"] - request["effective_date"]).days + 1 > MAX_MANUAL_GENERATION_DAYS:
		block("DATE_RANGE_EXCEEDED", f"Backdated period cannot exceed {MAX_MANUAL_GENERATION_DAYS} days.")


def _validate_employee_and_group(snapshot, request, block):
	employee = snapshot.get("employee") or {}
	group = snapshot.get("target_group") or {}
	if _value(employee, "status") != "Active":
		block("EMPLOYEE_NOT_ACTIVE", "Only active Employees can be transferred.")
	if not _value(group, "name") or _value(group, "name") != request["target_shift_group"]:
		block("TARGET_GROUP_MISSING", "Target Shift Group does not exist in the snapshot.")
	if int(_value(group, "disabled", 0) or 0):
		block("TARGET_GROUP_DISABLED", "Target Shift Group is disabled.")
	if _value(employee, "company") != _value(group, "company"):
		block("COMPANY_MISMATCH", "Employee Company differs from target Shift Group Company.")
	if _value(group, "effective_from") and request["effective_date"] < _to_date(_value(group, "effective_from")):
		block("TARGET_GROUP_OUTSIDE_PERIOD", "Effective Date is before target Shift Group period.")
	if _value(group, "effective_to") and request["membership_end_date"] > _to_date(_value(group, "effective_to")):
		block("TARGET_GROUP_OUTSIDE_PERIOD", "Membership End Date is after target Shift Group period.")


def _plan_membership(snapshot, request, block):
	memberships = [
		row
		for row in snapshot.get("memberships") or []
		if _value(row, "status") == "Active"
		and _ranges_overlap(
			_to_date(_value(row, "from_date")),
			_to_date(_value(row, "to_date")) if _value(row, "to_date") else date.max,
			request["effective_date"],
			request["membership_end_date"],
		)
	]
	current = [
		row
		for row in memberships
		if _to_date(_value(row, "from_date")) <= request["effective_date"]
		and (
			not _value(row, "to_date")
			or _to_date(_value(row, "to_date")) >= request["effective_date"]
		)
	]
	if len(current) > 1:
		block(
			"OVERLAPPING_MEMBERSHIPS",
			"Multiple active Shift Group memberships overlap Effective Date.",
			references=[_value(row, "name") for row in current],
		)
	source = current[0] if len(current) == 1 else None
	other = [row for row in memberships if row is not source]
	if other:
		block(
			"FUTURE_MEMBERSHIP_OVERLAP",
			"Another active membership overlaps the requested period.",
			references=[_value(row, "name") for row in other],
		)
	action = "CREATE_TARGET"
	if source and _value(source, "shift_group") == request["target_shift_group"]:
		source_to_date = (
			_to_date(_value(source, "to_date"))
			if _value(source, "to_date")
			else date.max
		)
		action = (
			"ALREADY_TARGET"
			if source_to_date >= request["membership_end_date"]
			else "EXTEND_TARGET"
		)
	elif source:
		action = (
			"INACTIVATE_SOURCE_CREATE_TARGET"
			if _to_date(_value(source, "from_date")) == request["effective_date"]
			else "CLOSE_SOURCE_CREATE_TARGET"
		)
	return {
		"action": action,
		"source_membership": _value(source, "name") if source else None,
		"source_shift_group": _value(source, "shift_group") if source else None,
		"source_end_date": (
			(request["effective_date"] - timedelta(days=1)).isoformat()
			if source and action == "CLOSE_SOURCE_CREATE_TARGET"
			else None
		),
		"target_shift_group": request["target_shift_group"],
		"target_from_date": request["effective_date"].isoformat(),
		"target_to_date": request["membership_end_date"].isoformat(),
	}


def _current_day_checkins_to_preserve(
	checkins,
	attendance_by_name,
	target_plan,
	request,
):
	"""Return today's punches that stay as raw logs for today's target shift.

	Today's Attendance is not built here; the daily pipeline builds it later from
	the rewritten plan. Only the tail of yesterday's overnight shift is consumed
	by the rebuild now, so it is not listed as preserved.
	"""
	preserved = []
	windows = _build_target_ownership_windows(target_plan, request)
	for row in checkins:
		log_time = _to_datetime(_value(row, "time"))
		if not log_time or log_time.date() != request["today"]:
			continue
		linked = attendance_by_name.get(_value(row, "attendance"))
		if linked and _to_date(_value(linked, "attendance_date")) < request["today"]:
			continue
		selected = select_checkin_window(
			SimpleNamespace(time=log_time, log_type=_value(row, "log_type") or ""),
			windows,
		)
		if selected and selected.work_date < request["today"]:
			continue
		if _value(row, "name"):
			preserved.append(_value(row, "name"))
	return preserved


def _build_target_ownership_windows(target_plan, request):
	windows = []
	for work_date in (
		request["today"] - timedelta(days=1),
		request["today"],
	):
		plan = target_plan.get(work_date) or {}
		shift_doc = plan.get("shift_doc")
		if plan.get("is_off") or not shift_doc:
			continue
		start = _to_time(_value(shift_doc, "start_time"))
		end = _to_time(_value(shift_doc, "end_time"))
		if not start or not end:
			continue
		start_datetime = datetime.combine(work_date, start)
		end_datetime = datetime.combine(work_date, end)
		if end <= start:
			end_datetime += timedelta(days=1)
		shift_doc_values = dict(shift_doc)
		shift_doc_values.setdefault("determine_check_in_and_check_out", "")
		windows.append(
			SimpleNamespace(
				employee=_value(request, "employee"),
				work_date=work_date,
				shift_type=plan.get("shift_type"),
				shift_doc=SimpleNamespace(**shift_doc_values),
				start_datetime=start_datetime,
				end_datetime=end_datetime,
				is_overnight=end_datetime.date() > work_date,
				is_off=False,
			)
		)
	return windows


def _uses_department_sunday_workday_policy(
	employee,
	target_group,
	work_date,
	is_off,
	shift_types,
):
	return bool(
		is_off
		and work_date.weekday() == 6
		and target_group == SUNDAY_WORKDAY_SHIFT_GROUP
		and _value(employee, "department") in SUNDAY_WORKDAY_DEPARTMENTS
		and _value(employee, "default_shift") in shift_types
	)


def _validate_confirmations(snapshot, effective_date, completed_through, block):
	protected = []
	for row in snapshot.get("confirmations") or []:
		work_date = _to_date(_value(row, "work_date") or _value(row, "date"))
		result = _value(row, "hr_result") or _value(row, "result") or _value(row, "ket_qua_hr")
		if work_date and effective_date <= work_date <= completed_through and str(result or "").strip():
			protected.append(_value(row, "name"))
	if protected:
		block(
			"CONFIRMED_ATTENDANCE_EXPLANATION",
			"An HR-confirmed attendance explanation exists in the rebuild period.",
			references=protected,
		)


def _validate_salary_slips(snapshot, effective_date, completed_through, block):
	protected = []
	for row in snapshot.get("salary_slips") or []:
		if int(_value(row, "docstatus", 0) or 0) != 1:
			continue
		if _ranges_overlap(
			_to_date(_value(row, "start_date")),
			_to_date(_value(row, "end_date")),
			effective_date,
			completed_through,
		):
			protected.append(_value(row, "name"))
	if protected:
		block(
			"SUBMITTED_SALARY_SLIP",
			"A submitted Salary Slip covers the rebuild period.",
			references=protected,
		)


def _attendance_is_provenanced(attendance, assignments, linked_logs):
	if int(_value(attendance, "custom_vnt_generated_by_pipeline", 0) or 0) and _value(
		attendance, "custom_vnt_source_shift_assignment"
	):
		return any(
			_value(row, "name") == _value(attendance, "custom_vnt_source_shift_assignment")
			and _is_engine_assignment(row)
			for row in assignments
		)
	if not linked_logs:
		return False
	return any(
		_is_engine_assignment(row)
		and _value(row, "shift_type") == _value(attendance, "shift")
		for row in assignments
	)


def _attendance_has_protected_source(attendance):
	return bool(
		_value(attendance, "leave_application")
		or _value(attendance, "attendance_request")
		or _value(attendance, "leave_type")
		or _value(attendance, "status") in {"On Leave", "Work From Home"}
	)


def _assignments_by_date(assignments, from_date, to_date):
	result = {}
	for row in assignments:
		if int(_value(row, "docstatus", 0) or 0) >= 2:
			continue
		start = max(_to_date(_value(row, "start_date")), from_date)
		end = min(
			_to_date(_value(row, "end_date")) if _value(row, "end_date") else to_date,
			to_date,
		)
		for work_date in _date_range(start, end):
			result.setdefault(work_date, []).append(row)
	return result


def _is_engine_assignment(row):
	return bool(
		int(_value(row, "custom_generated_by_shift_group", 0) or 0)
		and _value(row, "custom_assignment_source") == AUTO_ASSIGNMENT_SOURCE
	)


def _is_overnight(shift_doc):
	if not shift_doc:
		return False
	start = _to_time(_value(shift_doc, "start_time"))
	end = _to_time(_value(shift_doc, "end_time"))
	return bool(start and end and end <= start)


def _log_fits_previous_overnight_tail(log_time, plan):
	shift_doc = plan.get("shift_doc") if plan else None
	if not _is_overnight(shift_doc):
		return False
	end = _to_time(_value(shift_doc, "end_time"))
	allow_after = int(_value(shift_doc, "allow_check_out_after_shift_end_time", 0) or 0)
	actual_end = datetime.combine(log_time.date(), end) + timedelta(minutes=allow_after)
	return log_time <= actual_end


def _normalize_request(request):
	result = dict(request or {})
	employees = result.get("employees") or []
	if isinstance(employees, str):
		employees = [employees]
	result["employees"] = sorted(set(employees))
	for fieldname in ("effective_date", "membership_end_date", "generate_until", "today"):
		if result.get(fieldname):
			result[fieldname] = _to_date(result[fieldname])
	result["generate_until"] = result.get("generate_until") or result.get("membership_end_date")
	return result


def _canonicalize(value):
	if isinstance(value, Mapping):
		return {str(key): _canonicalize(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
	if isinstance(value, (list, tuple, set, frozenset)):
		items = [_canonicalize(item) for item in value]
		return sorted(items, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))
	if isinstance(value, datetime):
		return value.isoformat(sep=" ")
	if isinstance(value, (date, time)):
		return value.isoformat()
	if isinstance(value, timedelta):
		return {
			"__timedelta_microseconds__": (
				(value.days * 86_400 + value.seconds) * 1_000_000
				+ value.microseconds
			),
		}
	if isinstance(value, bytes):
		return value.decode("utf-8", errors="replace")
	return value


def _value(row, fieldname, default=None):
	if isinstance(row, Mapping):
		return row.get(fieldname, default)
	return getattr(row, fieldname, default)


def _to_date(value):
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	if value is None:
		return None
	return date.fromisoformat(str(value)[:10])


def _to_datetime(value):
	if isinstance(value, datetime):
		return value
	if not value:
		return None
	return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _to_time(value):
	if isinstance(value, time):
		return value
	if isinstance(value, timedelta):
		seconds = int(value.total_seconds()) % (24 * 60 * 60)
		return time(seconds // 3600, (seconds % 3600) // 60, seconds % 60)
	if not value:
		return None
	return time.fromisoformat(str(value))


def _date_range(from_date, to_date):
	if from_date is None or to_date is None or from_date > to_date:
		return
	current = from_date
	while current <= to_date:
		yield current
		current += timedelta(days=1)


def _month_keys(from_date, to_date):
	if from_date > to_date:
		return []
	keys = []
	cursor = from_date.replace(day=1)
	while cursor <= to_date:
		keys.append(cursor.strftime("%Y-%m"))
		cursor = (
			date(cursor.year + 1, 1, 1)
			if cursor.month == 12
			else date(cursor.year, cursor.month + 1, 1)
		)
	return keys


def _ranges_overlap(start_a, end_a, start_b, end_b):
	return bool(start_a and end_a and start_b and end_b and start_a <= end_b and start_b <= end_a)
