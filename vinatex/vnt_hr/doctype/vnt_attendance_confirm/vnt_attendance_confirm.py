"""One-level HR confirmation for abnormal biometric punches.

This DocType is deliberately an audit/approval layer. It does not create,
cancel, or alter Attendance because the shift-aware attendance pipeline is the
single source responsible for that data.
"""

from __future__ import annotations

from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_datetime, getdate, now_datetime, today

from vinatex.vnt_hr.attendance_processing import (
	build_shift_windows,
	calculate_attendance_details,
	classify_work_date,
	get_active_employees,
	get_log_presence,
	load_checkins_for_windows,
	load_holiday_context,
)


HR_ROLES = {"HR User", "HR Manager", "System Manager"}
PRESENCE_ONLY_ADMIN_DEPARTMENTS = frozenset(
	{
		"Vào bông - NMSVNĐ",
		"Công đoạn Đóng gói - NMSVNĐ",
	}
)


class VNTAttendanceConfirm(Document):
	def before_save(self):
		self.status = _compute_status(self)
		self.month = f"{getdate(self.from_date).month:02d}" if self.from_date else None
		self.year = getdate(self.from_date).year if self.from_date else None

		previous = self.get_doc_before_save()
		previous_rows = {
			row.name: row.get("confirm")
			for row in (previous.get("items") or [])
		} if previous else {}

		for row in self.get("items") or []:
			if row.get("confirm") and not row.get("type"):
				frappe.throw(
					_("Vui lòng nhập giải trình/căn cứ trước khi xác nhận ngày {0}.").format(
						frappe.format_value(row.date, {"fieldtype": "Date"})
					)
				)
			if row.get("confirm") != previous_rows.get(row.name):
				if row.get("confirm"):
					row.reviewed_by = frappe.session.user
					row.reviewed_on = now_datetime()
				else:
					row.reviewed_by = None
					row.reviewed_on = None

		previous_status = previous.get("status") if previous else None
		if self.status == "Đã xác nhận":
			if previous_status != "Đã xác nhận" or not self.reviewed_by:
				self.reviewed_by = frappe.session.user
				self.reviewed_on = now_datetime()
		else:
			self.reviewed_by = None
			self.reviewed_on = None


def _compute_status(doc: Document) -> str:
	items = doc.get("items") or []
	if not items or any(not row.get("type") for row in items):
		return "Chờ giải trình"
	if any(not row.get("confirm") for row in items):
		return "Chờ xác nhận"
	return "Đã xác nhận"


def _assert_hr_access():
	if frappe.session.user == "Administrator":
		return
	if not HR_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("Chỉ người dùng Nhân sự được sử dụng chức năng này."), frappe.PermissionError)


@frappe.whitelist()
def make_attendance_confirm(
	from_date=None,
	to_date=None,
	employee=None,
	company=None,
	department=None,
	branch=None,
	dry_run=False,
):
	"""Detect and upsert the supported attendance-confirmation cases."""
	_assert_hr_access()
	from_date, to_date = _resolve_date_range(from_date, to_date)
	dry_run = cint(dry_run)
	employee_names = [employee] if employee else None
	employees = [
		row
		for row in get_active_employees(from_date, to_date, employee_names)
		if not cint(row.custom_need_check)
		and (not company or row.company == company)
		and (not department or row.department == department)
		and (not branch or row.branch == branch)
	]
	result = {
		"Từ ngày": from_date,
		"Đến ngày": to_date,
		"Số nhân sự kiểm tra": len(employees),
		"Số ngày bất thường": 0,
		"Ngày OFF có chấm công": 0,
		"Ngày làm việc chỉ có chấm công ngoài ca": 0,
		"Ngày làm việc không có chấm công": 0,
		"Ngày làm việc có chấm nhưng không xác định được vào/ra": 0,
		"Ngày làm việc thiếu giờ vào": 0,
		"Ngày làm việc thiếu giờ ra": 0,
		"Ngày làm việc về sớm": 0,
		"Ngày làm việc có chấm ngoài ca": 0,
		"Số phiếu tạo mới": 0,
		"Số phiếu cập nhật": 0,
		"Số phiếu đã xóa": 0,
	}
	if not employees:
		return result

	windows = build_shift_windows(employees, from_date, to_date)
	completed_cutoff = get_datetime(to_date) + timedelta(days=1)
	planned_map, outside_map, calendar_map = load_checkins_for_windows(
		employees,
		windows,
		from_date,
		to_date,
		include_calendar_logs=True,
		checkin_end_exclusive=completed_cutoff,
	)
	holiday_context = load_holiday_context(employees, windows, from_date, to_date)
	excused_days = _load_excused_days(employees, from_date, to_date)
	employee_map = {row.name: row for row in employees}
	issues_by_employee = {row.name: [] for row in employees}

	for employee_row in employees:
		for work_date in _date_range(from_date, to_date):
			key = (employee_row.name, work_date)
			if key in excused_days:
				continue
			window = windows.get(key)
			if (
				window
				and window.get("end_datetime")
				and get_datetime(window.end_datetime) > completed_cutoff
			):
				continue
			day_type = classify_work_date(employee_row, window, holiday_context)
			issue = _detect_confirmation_issue(
				employee=employee_row,
				window=window,
				planned_logs=planned_map.get(key, []),
				outside_logs=outside_map.get(key, []),
				calendar_logs=calendar_map.get(key, []),
				day_type=day_type,
			)
			if not issue:
				continue
			issue.date = work_date
			issues_by_employee[employee_row.name].append(issue)
			result[issue.counter_key] += 1
			result["Số ngày bất thường"] += 1

	if dry_run:
		return result

	for employee_name, issues in issues_by_employee.items():
		employee_row = employee_map[employee_name]
		created, updated, deleted = _upsert_employee_confirmation(
			employee_row, from_date, to_date, issues
		)
		result["Số phiếu tạo mới"] += created
		result["Số phiếu cập nhật"] += updated
		result["Số phiếu đã xóa"] += deleted

	return result


@frappe.whitelist()
def refresh_attendance_confirm(docname):
	"""Refresh one confirmation document from current shift/checkin data."""
	_assert_hr_access()
	doc = frappe.get_doc("VNT Attendance Confirm", docname)
	return make_attendance_confirm(
		from_date=doc.from_date,
		to_date=doc.to_date,
		employee=doc.employee,
	)


def _resolve_date_range(from_date=None, to_date=None):
	current = getdate(today())
	last_completed_date = current - timedelta(days=1)
	if from_date or to_date:
		if not from_date or not to_date:
			frappe.throw(_("Phải nhập đồng thời Từ ngày và Đến ngày."))
		from_date, to_date = getdate(from_date), getdate(to_date)
		to_date = min(to_date, last_completed_date)
	else:
		if current.day == 1:
			previous_month_end = current - timedelta(days=1)
			from_date = previous_month_end.replace(day=1)
			to_date = previous_month_end
		else:
			from_date = current.replace(day=1)
			to_date = current - timedelta(days=1)
		to_date = min(to_date, last_completed_date)
	if from_date > to_date:
		frappe.throw(_("Từ ngày không được sau Đến ngày."))
	if from_date.month != to_date.month or from_date.year != to_date.year:
		frappe.throw(_("Mỗi lần chỉ tạo giải trình trong cùng một tháng."))
	return from_date, to_date


def _uses_presence_only_admin_policy(employee, window) -> bool:
	return bool(
		employee
		and window
		and employee.get("department") in PRESENCE_ONLY_ADMIN_DEPARTMENTS
		and window.get("shift_type") == "Hành chính"
	)


def _detect_confirmation_issue(
	*,
	window,
	planned_logs,
	outside_logs,
	day_type,
	employee=None,
	calendar_logs=None,
):
	planned_logs = sorted(planned_logs or [], key=lambda row: get_datetime(row.time))
	outside_logs = sorted(outside_logs or [], key=lambda row: get_datetime(row.time))

	if day_type == "off":
		# A weekly OFF may still have a nominal Employee.default_shift window.
		# Any punch on an OFF day is outside the working plan regardless of which
		# technical bucket load_checkins_for_windows placed it in.
		off_logs = sorted(
			[*planned_logs, *outside_logs], key=lambda row: get_datetime(row.time)
		)
		if not off_logs:
			return None
		return _issue_payload(
			code="OFF_WITH_CHECKIN",
			label="Ngày OFF có chấm công ngoài ca",
			question="Xác nhận nhân sự có thực sự làm tăng ca trong ngày OFF?",
			counter_key="Ngày OFF có chấm công",
			window=window,
			planned_logs=[],
			outside_logs=off_logs,
		)

	# Holiday handling and further anomaly types can be added independently.
	if day_type != "work" or not window:
		return None

	if _uses_presence_only_admin_policy(employee, window):
		all_logs = (
			sorted(calendar_logs, key=lambda row: get_datetime(row.time))
			if calendar_logs is not None
			else [*planned_logs, *outside_logs]
		)
		has_in = any((row.get("log_type") or "").upper() == "IN" for row in all_logs)
		has_out = any((row.get("log_type") or "").upper() == "OUT" for row in all_logs)
		if has_in and has_out:
			return None
		if not has_in and not has_out:
			return _issue_payload(
				code="WORKDAY_NO_CHECKIN",
				label="Ngày làm việc không có chấm công",
				question="Xác nhận lý do nhân sự không có dữ liệu chấm công trong ngày?",
				counter_key="Ngày làm việc không có chấm công",
				window=window,
				planned_logs=all_logs,
				outside_logs=[],
			)
		if not has_in:
			return _issue_payload(
				code="MISSING_IN",
				label="Chỉ có giờ ra hợp lệ trong ngày",
				question="Xác nhận nhân sự có thực sự đi làm và bị thiếu giờ vào?",
				counter_key="Ngày làm việc thiếu giờ vào",
				window=window,
				planned_logs=all_logs,
				outside_logs=[],
			)
		return _issue_payload(
			code="MISSING_OUT",
			label="Chỉ có giờ vào hợp lệ trong ngày",
			question="Xác nhận nhân sự có thực sự đi làm và bị thiếu giờ ra?",
			counter_key="Ngày làm việc thiếu giờ ra",
			window=window,
			planned_logs=all_logs,
			outside_logs=[],
		)

	if not planned_logs and outside_logs:
		return _issue_payload(
			code="WORKDAY_OUTSIDE_ONLY",
			label="Ngày làm việc chỉ có chấm công ngoài ca",
			question="Xác nhận nhân sự có thực sự đi làm trong ngày này?",
			counter_key="Ngày làm việc chỉ có chấm công ngoài ca",
			window=window,
			planned_logs=planned_logs,
			outside_logs=outside_logs,
		)

	if not planned_logs:
		return _issue_payload(
			code="WORKDAY_NO_CHECKIN",
			label="Ngày làm việc không có chấm công",
			question="Xác nhận lý do nhân sự không có dữ liệu chấm công trong ngày?",
			counter_key="Ngày làm việc không có chấm công",
			window=window,
			planned_logs=planned_logs,
			outside_logs=outside_logs,
		)

	has_in, has_out = get_log_presence(window, planned_logs)
	if has_in and has_out:
		details = calculate_attendance_details(
			window, planned_logs, respect_marking_flags=False
		)
		if outside_logs:
			return _issue_payload(
				code="WORKDAY_OVERTIME",
				label="Ngày làm việc có chấm công ngoài ca",
				question="Xác nhận thời gian chấm ngoài ca có được công nhận làm tăng ca?",
				counter_key="Ngày làm việc có chấm ngoài ca",
				window=window,
				planned_logs=planned_logs,
				outside_logs=outside_logs,
			)
		# Sm is a complete work pair whose OUT punch is earlier than the
		# planned end minus the Shift Type grace period.  It is different from
		# a missing punch: HR may waive only the early-exit exception while the
		# original Checkins and Attendance remain unchanged.
		if details.status == "Present" and details.early_exit:
			return _issue_payload(
				code="EARLY_EXIT",
				label="Về sớm so với ca kế hoạch",
				question=(
					"Xác nhận có căn cứ hợp lệ để công nhận đủ công "
					"và chuyển ký hiệu Sm thành X?"
				),
				counter_key="Ngày làm việc về sớm",
				window=window,
				planned_logs=planned_logs,
				outside_logs=outside_logs,
			)
		return None
	if not has_in and not has_out:
		return _issue_payload(
			code="WORKDAY_INVALID_CHECKINS",
			label="Có chấm trong ca nhưng không xác định được giờ vào/ra",
			question="Xác nhận nhân sự có thực sự đi làm trong ngày này?",
			counter_key="Ngày làm việc có chấm nhưng không xác định được vào/ra",
			window=window,
			planned_logs=planned_logs,
			outside_logs=outside_logs,
		)
	if not has_in:
		return _issue_payload(
			code="MISSING_IN",
			label="Chỉ có giờ ra hợp lệ trong ca",
			question="Xác nhận nhân sự có thực sự đi làm và bị thiếu giờ vào?",
			counter_key="Ngày làm việc thiếu giờ vào",
			window=window,
			planned_logs=planned_logs,
			outside_logs=outside_logs,
		)
	return _issue_payload(
		code="MISSING_OUT",
		label="Chỉ có giờ vào hợp lệ trong ca",
		question="Xác nhận nhân sự có thực sự đi làm và bị thiếu giờ ra?",
		counter_key="Ngày làm việc thiếu giờ ra",
		window=window,
		planned_logs=planned_logs,
		outside_logs=outside_logs,
	)


def _issue_payload(
	*, code, label, question, counter_key, window, planned_logs, outside_logs
):
	details = None
	if window and planned_logs:
		details = calculate_attendance_details(
			window, planned_logs, respect_marking_flags=False
		)
	all_logs = sorted([*planned_logs, *outside_logs], key=lambda row: get_datetime(row.time))
	first_log = get_datetime(all_logs[0].time) if all_logs else None
	last_log = get_datetime(all_logs[-1].time) if len(all_logs) > 1 else None
	evidence_code = ""
	if outside_logs:
		evidence_code = "+1" if len(outside_logs) == 1 else "+"
	return frappe._dict(
		issue_code=code,
		issue_type=label,
		decision_question=question,
		counter_key=counter_key,
		shift_group=window.get("shift_group") if window else None,
		planned_shift=window.get("shift_type") if window else None,
		day_type="Ngày OFF" if code == "OFF_WITH_CHECKIN" else "Ngày làm việc",
		planned_checkin_count=len(planned_logs),
		outside_checkin_count=len(outside_logs),
		evidence_code=evidence_code,
		checkin_summary=_format_checkin_summary(planned_logs, outside_logs),
		time_in=(details.in_time if details else first_log),
		time_out=(details.out_time if details else last_log),
		status=label,
	)


def _format_checkin_summary(planned_logs, outside_logs):
	def format_group(logs):
		return ", ".join(
			f"{get_datetime(row.time).strftime('%d/%m %H:%M')}"
			+ (f" {row.log_type}" if row.get("log_type") else "")
			for row in logs
		) or "Không có"

	return "Trong ca: {0} | Ngoài ca: {1}".format(
		format_group(planned_logs), format_group(outside_logs)
	)


def _upsert_employee_confirmation(
	employee, from_date, to_date, issues
) -> tuple[int, int, int]:
	name = frappe.db.get_value(
		"VNT Attendance Confirm",
		{
			"employee": employee.name,
			"from_date": from_date,
			"docstatus": ["<", 2],
		},
		"name",
	)
	doc = (
		frappe.get_doc("VNT Attendance Confirm", name, for_update=True)
		if name
		else None
	)
	if not doc and not issues:
		return 0, 0, 0
	if not doc:
		doc = frappe.new_doc("VNT Attendance Confirm")
		doc.employee = employee.name
		doc.employee_name = employee.employee_name
		doc.company = employee.company
		doc.department = employee.department
		doc.from_date = from_date
		doc.to_date = to_date
		doc.month = f"{from_date.month:02d}"
		doc.year = from_date.year

	doc.to_date = to_date
	existing_by_date = {
		getdate(row.date): row for row in (doc.get("items") or []) if row.date
	}
	issue_dates = {issue.date for issue in issues}
	changed = not name

	# Remove only unresolved rows whose anomaly has disappeared. Confirmed rows
	# remain as an audit trail even if a later biometric sync resolves it.
	for row in list(doc.get("items") or []):
		if getdate(row.date) not in issue_dates and not row.get("confirm"):
			doc.remove(row)
			changed = True

	for issue in issues:
		row = existing_by_date.get(issue.date)
		if not row:
			row = doc.append("items", {})
			row.date = issue.date
			changed = True
		for fieldname in (
			"issue_code",
			"issue_type",
			"decision_question",
			"shift_group",
			"planned_shift",
			"day_type",
			"planned_checkin_count",
			"outside_checkin_count",
			"evidence_code",
			"checkin_summary",
			"time_in",
			"time_out",
			"status",
		):
			value = issue.get(fieldname)
			if row.get(fieldname) != value:
				row.set(fieldname, value)
				changed = True

	if name and not (doc.get("items") or []):
		frappe.delete_doc(
			"VNT Attendance Confirm", name, ignore_permissions=True
		)
		return 0, 0, 1

	if not changed:
		return 0, 0, 0
	doc.flags.ignore_permissions = True
	if name:
		doc.save(ignore_permissions=True)
		return 0, 1, 0
	doc.insert(ignore_permissions=True)
	return 1, 0, 0


def _load_excused_days(employees, from_date, to_date):
	employee_names = [row.name for row in employees]
	if not employee_names:
		return set()
	excused = set()
	leaves = frappe.get_all(
		"Leave Application",
		filters={
			"employee": ["in", employee_names],
			"from_date": ["<=", to_date],
			"to_date": [">=", from_date],
			"docstatus": 1,
		},
		fields=["employee", "from_date", "to_date", "half_day", "half_day_date"],
	)
	for leave in leaves:
		for work_date in _date_range(
			max(from_date, getdate(leave.from_date)),
			min(to_date, getdate(leave.to_date)),
		):
			if cint(leave.half_day) and getdate(leave.half_day_date) == work_date:
				continue
			excused.add((leave.employee, work_date))

	if frappe.db.exists("DocType", "VNT Business Trip Request"):
		trips = frappe.get_all(
			"VNT Business Trip Request",
			filters={
				"employee": ["in", employee_names],
				"from_date": ["<=", to_date],
				"to_date": [">=", from_date],
				"docstatus": 1,
			},
			fields=["employee", "from_date", "to_date"],
		)
		for trip in trips:
			for work_date in _date_range(
				max(from_date, getdate(trip.from_date)),
				min(to_date, getdate(trip.to_date)),
			):
				excused.add((trip.employee, work_date))
	return excused


def _date_range(from_date, to_date):
	current = getdate(from_date)
	to_date = getdate(to_date)
	while current <= to_date:
		yield current
		current += timedelta(days=1)


# Kept for integrations that used the previous public helper.
@frappe.whitelist()
def get_working_dates_of_month():
	from_date, to_date = _resolve_date_range()
	return list(_date_range(from_date, to_date))


def min_max_date(dates):
	dates = [getdate(value) for value in dates if value]
	return (min(dates), max(dates)) if dates else (None, None)
