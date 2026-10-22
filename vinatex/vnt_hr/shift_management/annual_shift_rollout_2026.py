"""Idempotent declaration of Kíp, weekly OFF/holidays and Shift Assignments for 2026.

Scope (approved by HR on 20/10/2026):

* Every active Employee gets explicit, contiguous VNT Shift Group Assignment
  history from ``max(01/01/2026, date_of_joining)`` to 31/12/2026.
* Employees without a Kíp are administrative staff and join "HC"; the ones in
  ``UNCLEAR_EMPLOYEES`` are left untouched for HR to decide.
* Before an existing membership, the Kíp is taken from the employee's earliest
  generated Shift Assignments; when there is no such evidence the gap is reported.
* ``Employee.holiday_list``: HC staff use "2026" (Sundays + public holidays),
  Kíp staff use the Holiday List of their current Kíp.
* Shift Assignments are generated with the standard engine for the whole
  membership period. HC staff do not get a shift on public holidays.

    bench --site <site> execute vinatex.vnt_hr.shift_management.annual_shift_rollout_2026.plan
    bench --site <site> execute vinatex.vnt_hr.shift_management.annual_shift_rollout_2026.apply_memberships
    bench --site <site> execute vinatex.vnt_hr.shift_management.annual_shift_rollout_2026.generate
    bench --site <site> execute vinatex.vnt_hr.shift_management.annual_shift_rollout_2026.verify
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import getdate

from vinatex.vnt_hr.shift_management.constants import AUTO_ASSIGNMENT_SOURCE, WEEKDAYS
from vinatex.vnt_hr.shift_management.shift_assignment_service import generate_shift_assignments

COMPANY = "Nhà máy Sợi Vinatex Nam Định"
YEAR_FROM = getdate("2026-01-01")
YEAR_TO = getdate("2026-12-31")
HC_GROUP = "HC"
HC_HOLIDAY_LIST = "2026"
NOTE = "Khai báo Kíp năm 2026 theo xác nhận của HR ngày 20/10/2026."

# Not clearly administrative staff; HR decides their Kíp separately.
UNCLEAR_EMPLOYEES = {
	"NMSVNĐ00022": "Trần Văn Tiến - Trưởng ca",
	"NMSVNĐ00167": "Hà Tiến Đạt - Phó trưởng ca",
	"NMSVNĐ00050": "Nguyễn Thị Minh - ca Vệ sinh",
	"NMSVNĐ00163": "Vũ Trịnh Ngọc Hà - Bộ phận Điện",
	"NMSVNĐ00165": "Đỗ Mạnh Hùng - Bộ phận Điện",
	"NMSVNĐ00177": "Nguyễn Xuân Khanh - chưa có chức danh",
}

# Kíp before the first membership when generated assignments give no evidence.
# HR confirmed on 20/10/2026 that the current special Kíp applied from the start.
PRIOR_GROUP_OVERRIDES = {
	"NMSVNĐ00048": "ĐB Điện - Nghỉ T3",  # Trần Ngọc Tuyền
	"NMSVNĐ00159": "ĐB HC-Đêm - Nghỉ T7",  # Lại Văn Hiệp
	"NMSVNĐ00164": "ĐB Điện - Nghỉ T5",  # Bùi Ngọc An
	"NMSVNĐ00168": "ĐB Điện - Nghỉ CN",  # Nguyễn Hải Đăng
}

GENERATION_BATCH_SIZE = 5


def plan() -> dict:
	"""Read-only: memberships to create, Employee fields to set and open gaps."""
	result = _build_plan()
	return {
		"status": "READY" if not result["blocked"] else "BLOCKED",
		"memberships_to_create": len(result["memberships"]),
		"memberships_by_group": dict(Counter(row["shift_group"] for row in result["memberships"])),
		"employee_updates": len(result["employee_updates"]),
		"gaps_not_covered": result["gaps"],
		"skipped_unclear": result["skipped"],
		"blocked": result["blocked"],
		"memberships": result["memberships"],
	}


def apply_memberships() -> dict:
	"""Create memberships, set HC group/Employee holiday lists. Safe to re-run."""
	result = _build_plan()
	if result["blocked"]:
		frappe.throw(_("Annual shift rollout plan is blocked: {0}").format(result["blocked"][:10]))

	if frappe.db.get_value("VNT Shift Group", HC_GROUP, "holiday_list") != HC_HOLIDAY_LIST:
		# Holiday List is not part of the "used schedule" guard; only reports and
		# the HC public-holiday skip below read it.
		frappe.db.set_value("VNT Shift Group", HC_GROUP, "holiday_list", HC_HOLIDAY_LIST)

	for row in result["memberships"]:
		frappe.get_doc(
			{
				"doctype": "VNT Shift Group Assignment",
				"employee": row["employee"],
				"employee_name": row["employee_name"],
				"company": COMPANY,
				"shift_group": row["shift_group"],
				"from_date": row["from_date"],
				"to_date": row["to_date"],
				"status": "Active",
				"note": NOTE,
			}
		).insert(ignore_permissions=True)

	for employee, values in result["employee_updates"].items():
		frappe.db.set_value("Employee", employee, values, update_modified=True)

	return {
		"status": "COMPLETED",
		"memberships_created": len(result["memberships"]),
		"employees_updated": len(result["employee_updates"]),
		"gaps_not_covered": result["gaps"],
	}


def generate(employees=None) -> dict:
	"""Generate missing Shift Assignments for every managed membership period.

	Runs in small committed batches so a long backfill can be resumed; the
	engine is idempotent and skips days that already have an assignment.
	"""
	periods = _membership_periods(employees)
	public_holidays = _public_holidays(HC_HOLIDAY_LIST)
	counts = Counter()
	errors = []
	names = sorted(periods)
	for offset in range(0, len(names), GENERATION_BATCH_SIZE):
		for employee in names[offset : offset + GENERATION_BATCH_SIZE]:
			for from_date, to_date, shift_group in periods[employee]:
				skip = public_holidays if shift_group == HC_GROUP else set()
				for segment_from, segment_to in _segments(from_date, to_date, skip):
					result = generate_shift_assignments(
						segment_from, segment_to, employees=[employee], preview=False
					)
					counts.update(result.get("counts", {}))
					errors.extend(
						{"employee": employee, "date": row["date"], "reason": row["reason"]}
						for row in result.get("rows", [])
						if row["action"] == "ERROR"
					)
		frappe.db.commit()  # nosemgrep: one-time resumable backfill, committed per batch
	return {"status": "COMPLETED" if not errors else "ERRORS", "counts": dict(counts), "errors": errors[:50]}


def verify() -> dict:
	"""Every managed day has exactly the planned shift (or none on OFF/holiday)."""
	periods = _membership_periods()
	public_holidays = _public_holidays(HC_HOLIDAY_LIST)
	schedules = _schedules()
	assignments = defaultdict(list)
	for row in frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": ["in", list(periods)],
			"start_date": ["between", [YEAR_FROM, YEAR_TO]],
			"docstatus": 1,
		},
		fields=["employee", "start_date", "end_date", "shift_type", "custom_shift_group", "custom_assignment_source"],
	):
		assignments[(row.employee, row.start_date)].append(row)

	mismatches = []
	checked_days = 0
	for employee, employee_periods in periods.items():
		for from_date, to_date, shift_group in employee_periods:
			work_date = from_date
			while work_date <= to_date:
				checked_days += 1
				expected = schedules[(shift_group, WEEKDAYS[work_date.weekday()])]
				if shift_group == HC_GROUP and work_date in public_holidays:
					expected = None
				actual = assignments.get((employee, work_date), [])
				issue = None
				if expected is None and actual:
					issue = "EXPECTED_OFF"
				elif expected and len(actual) != 1:
					issue = f"ASSIGNMENT_COUNT={len(actual)}"
				elif expected and (
					actual[0].shift_type != expected
					or actual[0].custom_shift_group != shift_group
					or actual[0].start_date != actual[0].end_date
				):
					issue = f"VALUE {actual[0].shift_type}/{actual[0].custom_shift_group}"
				if issue:
					mismatches.append(
						{"employee": employee, "date": work_date, "group": shift_group, "expected": expected, "issue": issue}
					)
				work_date += timedelta(days=1)

	missing_holiday_list = frappe.get_all(
		"Employee",
		filters={"status": "Active", "company": COMPANY, "holiday_list": ["is", "not set"]},
		pluck="name",
	)
	return {
		"status": "PASS" if not mismatches else "FAIL",
		"employees": len(periods),
		"checked_days": checked_days,
		"mismatch_count": len(mismatches),
		"mismatches": mismatches[:100],
		"employees_without_holiday_list": missing_holiday_list,
		"unclear_not_declared": UNCLEAR_EMPLOYEES,
	}


def _build_plan() -> dict:
	groups = {
		row.name: row
		for row in frappe.get_all("VNT Shift Group", fields=["name", "holiday_list", "disabled"])
	}
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active", "company": COMPANY},
		fields=[
			"name",
			"employee_name",
			"date_of_joining",
			"custom_shift_group",
			"custom_working_schedule_type",
			"holiday_list",
		],
		order_by="name",
	)
	memberships = defaultdict(list)
	for row in frappe.get_all(
		"VNT Shift Group Assignment",
		filters={"status": "Active", "employee": ["in", [row.name for row in employees]]},
		fields=["name", "employee", "shift_group", "from_date", "to_date"],
		order_by="from_date asc",
	):
		memberships[row.employee].append(row)

	to_create, updates, gaps, skipped, blocked = [], {}, [], [], []
	for employee in employees:
		if employee.name in UNCLEAR_EMPLOYEES:
			skipped.append({"employee": employee.name, "reason": UNCLEAR_EMPLOYEES[employee.name]})
			continue

		start = max(YEAR_FROM, getdate(employee.date_of_joining) if employee.date_of_joining else YEAR_FROM)
		existing = memberships.get(employee.name, [])
		current_group = existing[-1].shift_group if existing else (employee.custom_shift_group or HC_GROUP)
		if current_group not in groups or groups[current_group].disabled:
			blocked.append({"employee": employee.name, "reason": f"Kíp không hợp lệ: {current_group}"})
			continue

		if not existing:
			to_create.append(_membership(employee, current_group, start, YEAR_TO))
		else:
			first_from = getdate(existing[0].from_date)
			if start < first_from:
				prior_group = _prior_group(employee.name, first_from) or PRIOR_GROUP_OVERRIDES.get(employee.name)
				if prior_group:
					to_create.append(_membership(employee, prior_group, start, first_from - timedelta(days=1)))
				else:
					gaps.append(
						{
							"employee": employee.name,
							"employee_name": employee.employee_name,
							"from_date": start,
							"to_date": first_from - timedelta(days=1),
							"reason": "Chưa có dữ liệu Kíp trước lịch hiện tại",
						}
					)
			for previous, following in zip(existing, existing[1:]):
				if getdate(previous.to_date) + timedelta(days=1) != getdate(following.from_date):
					blocked.append({"employee": employee.name, "reason": "Lịch sử Kíp bị hở hoặc chồng ngày"})
			if not existing[-1].to_date or getdate(existing[-1].to_date) < YEAR_TO:
				blocked.append({"employee": employee.name, "reason": "Kíp hiện tại không kéo dài đến 31/12/2026"})

		values = {}
		if employee.custom_shift_group != current_group:
			values["custom_shift_group"] = current_group
		schedule_type = _schedule_type(current_group, employee.custom_working_schedule_type)
		if employee.custom_working_schedule_type != schedule_type:
			values["custom_working_schedule_type"] = schedule_type
		holiday_list = groups[current_group].holiday_list
		if current_group == HC_GROUP:
			holiday_list = HC_HOLIDAY_LIST
		if holiday_list and employee.holiday_list != holiday_list:
			values["holiday_list"] = holiday_list
		if values:
			updates[employee.name] = values

	return {
		"memberships": to_create,
		"employee_updates": updates,
		"gaps": gaps,
		"skipped": skipped,
		"blocked": blocked,
	}


def _membership(employee, shift_group, from_date, to_date):
	return {
		"employee": employee.name,
		"employee_name": employee.employee_name,
		"shift_group": shift_group,
		"from_date": from_date,
		"to_date": to_date,
	}


def _prior_group(employee, before_date):
	"""Kíp proven by the generated assignments before the first membership."""
	groups = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": employee,
			"start_date": ["<", before_date],
			"docstatus": 1,
			"custom_assignment_source": AUTO_ASSIGNMENT_SOURCE,
		},
		distinct=True,
		pluck="custom_shift_group",
	)
	return groups[0] if len(groups) == 1 else None


def _schedule_type(shift_group, current):
	if shift_group == HC_GROUP:
		return "Hành chính"
	if shift_group in {str(index) for index in range(1, 8)}:
		return "Theo kíp"
	return current or "Lịch đặc biệt"


def _membership_periods(employees=None):
	active_employees = frappe.get_all("Employee", filters={"status": "Active", "company": COMPANY}, pluck="name")
	filters = {
		"status": "Active",
		"company": COMPANY,
		"employee": ["in", active_employees],
		"from_date": ["<=", YEAR_TO],
		"to_date": [">=", YEAR_FROM],
	}
	managed = set(frappe.get_all("VNT Shift Group Assignment", filters=filters, pluck="employee"))
	managed -= set(UNCLEAR_EMPLOYEES)
	if employees:
		managed &= set(frappe.parse_json(employees) if isinstance(employees, str) else employees)
	periods = defaultdict(list)
	for row in frappe.get_all(
		"VNT Shift Group Assignment",
		filters={"status": "Active", "employee": ["in", list(managed) or [""]]},
		fields=["employee", "shift_group", "from_date", "to_date"],
		order_by="from_date asc",
	):
		periods[row.employee].append(
			(max(getdate(row.from_date), YEAR_FROM), min(getdate(row.to_date), YEAR_TO), row.shift_group)
		)
	return periods


def _public_holidays(holiday_list):
	return {
		getdate(row.holiday_date)
		for row in frappe.get_all(
			"Holiday",
			filters={"parent": holiday_list, "weekly_off": 0, "holiday_date": ["between", [YEAR_FROM, YEAR_TO]]},
			fields=["holiday_date"],
		)
	}


def _schedules():
	return {
		(row.parent, row.day_of_week): (None if row.is_off else row.shift_type)
		for row in frappe.get_all(
			"VNT Shift Group Schedule",
			filters={"parenttype": "VNT Shift Group"},
			fields=["parent", "day_of_week", "shift_type", "is_off"],
		)
	}


def _segments(from_date, to_date, skip_dates):
	"""Split a period into contiguous ranges that avoid ``skip_dates``."""
	segment_start = None
	work_date = from_date
	while work_date <= to_date:
		if work_date in skip_dates:
			if segment_start:
				yield segment_start, work_date - timedelta(days=1)
				segment_start = None
		elif not segment_start:
			segment_start = work_date
		work_date += timedelta(days=1)
	if segment_start:
		yield segment_start, to_date
