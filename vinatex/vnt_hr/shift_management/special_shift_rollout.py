"""One-time, idempotent rollout of the approved 2026 special weekly shifts."""

from __future__ import annotations

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import getdate

from vinatex.vnt_hr.shift_management.constants import WEEKDAYS
from vinatex.vnt_hr.shift_management.shift_group_transfer_service import (
	_build_preview,
	_run_bulk_shift_group_transfer,
	_validate_request,
)

COMPANY = "Nhà máy Sợi Vinatex Nam Định"
EFFECTIVE_FROM = getdate("2026-10-14")
EFFECTIVE_TO = getdate("2026-12-31")

SPECIAL_SHIFT_GROUPS = {
	"ĐB Điện - Nghỉ T3": {
		"holiday_list": "KIP-04-2026",
		"schedule": ("Đêm", None, "Sáng", "Sáng", "Sáng", "Đêm", "Đêm"),
	},
	"ĐB HC-Đêm - Nghỉ T6": {
		"holiday_list": "KIP-01-2026",
		"schedule": ("Hành chính", "Hành chính", "Hành chính", "Đêm", None, "Hành chính", "Hành chính"),
	},
	"ĐB Kíp 7 Sáng - Nghỉ T7": {
		"holiday_list": "KIP-07-2026",
		"schedule": ("Sáng", "Chiều", "Chiều", "Sáng", "Sáng", None, "Sáng"),
	},
	"TT - Nghỉ T2": {
		"holiday_list": "KIP-05-2026",
		"schedule": (None, "Chiều", "Chiều", "Chiều", "Đêm", "Đêm", "Đêm"),
	},
	"TT - Nghỉ T3": {
		"holiday_list": "KIP-04-2026",
		"schedule": ("Đêm", None, "Chiều", "Chiều", "Chiều", "Đêm", "Đêm"),
	},
	"TT - Nghỉ T4": {
		"holiday_list": "KIP-03-2026",
		"schedule": ("Đêm", "Đêm", None, "Chiều", "Chiều", "Chiều", "Đêm"),
	},
	"TT - Nghỉ T5": {
		"holiday_list": "KIP-02-2026",
		"schedule": ("Đêm", "Đêm", "Đêm", None, "Chiều", "Chiều", "Chiều"),
	},
	"TT - Nghỉ T6": {
		"holiday_list": "KIP-01-2026",
		"schedule": ("Chiều", "Đêm", "Đêm", "Đêm", None, "Chiều", "Chiều"),
	},
	"TT - Nghỉ T7": {
		"holiday_list": "KIP-07-2026",
		"schedule": ("Chiều", "Chiều", "Đêm", "Đêm", "Đêm", None, "Chiều"),
	},
	"TT - Nghỉ CN": {
		"holiday_list": "KIP-06-2026",
		"schedule": ("Chiều", "Chiều", "Chiều", "Đêm", "Đêm", "Đêm", None),
	},
}

SPECIAL_EMPLOYEES = {
	"NMSVNĐ00048": ("Trần Ngọc Tuyền", "ĐB Điện - Nghỉ T3"),
	"NMSVNĐ00159": ("Lại Văn Hiệp", "ĐB HC-Đêm - Nghỉ T6"),
	"NMSVNĐ00146": ("Trần Thị Ngà", "ĐB Kíp 7 Sáng - Nghỉ T7"),
	"NMSVNĐ00148": ("Trần Thị Tuyết Minh", "TT - Nghỉ T2"),
	"NMSVNĐ00129": ("Vũ Thị Lụa", "TT - Nghỉ T3"),
	"NMSVNĐ00145": ("Đỗ Thị Ánh Tuyết", "TT - Nghỉ T4"),
	"NMSVNĐ00080": ("Trần Văn Thanh", "TT - Nghỉ T5"),
	"NMSVNĐ00078": ("Nguyễn Duy Tư", "TT - Nghỉ T6"),
	"NMSVNĐ00144": ("Đặng Thị Xuyến", "TT - Nghỉ T7"),
	"NMSVNĐ00077": ("Trần Duy Quang", "TT - Nghỉ CN"),
}


def setup_special_shift_groups() -> dict:
	"""Create missing special masters and refuse to overwrite any conflict."""
	_validate_dependencies()
	results = []
	for group_name, definition in SPECIAL_SHIFT_GROUPS.items():
		expected_schedule = _schedule_rows(definition["schedule"])
		if frappe.db.exists("VNT Shift Group", group_name):
			differences = _compare_group(group_name, definition, expected_schedule)
			if differences:
				frappe.throw(
					_("Special Shift Group {0} already exists with conflicts: {1}").format(
						group_name, differences
					)
				)
			results.append({"shift_group": group_name, "status": "MATCH"})
			continue

		doc = frappe.get_doc(
			{
				"doctype": "VNT Shift Group",
				"shift_group_name": group_name,
				"company": COMPANY,
				"holiday_list": definition["holiday_list"],
				"effective_from": EFFECTIVE_FROM,
				"effective_to": EFFECTIVE_TO,
				"description": "Lịch đặc biệt 2026 đã được đối chiếu với bảng phân kíp của HR.",
				"schedule": expected_schedule,
			}
		)
		doc.insert(ignore_permissions=True)
		results.append({"shift_group": doc.name, "status": "CREATED"})

	return {"status": "OK", "groups": results}


def preview_special_shift_rollout() -> dict:
	"""Preview every one-person transfer without changing employee data."""
	_validate_dependencies(require_groups=True)
	previews = []
	for employee, (employee_name, shift_group) in SPECIAL_EMPLOYEES.items():
		_validate_employee(employee, employee_name)
		request = _request(employee, shift_group)
		preview = _build_preview(request)
		preview.pop("assignment_names_to_cancel", None)
		previews.append(preview)
	return {
		"status": "READY"
		if all(item["counts"].get("BLOCKED", 0) == 0 for item in previews)
		else "BLOCKED",
		"effective_from": EFFECTIVE_FROM,
		"effective_to": EFFECTIVE_TO,
		"employees": len(previews),
		"auto_assignments_to_cancel": sum(item["auto_assignments_to_cancel"] for item in previews),
		"previews": previews,
	}


def execute_special_shift_rollout() -> dict:
	"""Transfer all ten employees and synchronize their display/fallback fields."""
	preview = preview_special_shift_rollout()
	if preview["status"] != "READY":
		frappe.throw(_("Special shift rollout preview is blocked; nothing was changed."))

	results = []
	for employee, (employee_name, shift_group) in SPECIAL_EMPLOYEES.items():
		result = _run_bulk_shift_group_transfer(
			_request(employee, shift_group), requested_by=frappe.session.user
		)
		results.append({"employee": employee, "employee_name": employee_name, **result})

	for employee, (_employee_name, shift_group) in SPECIAL_EMPLOYEES.items():
		frappe.db.set_value(
			"Employee",
			employee,
			{
				"custom_working_schedule_type": "Lịch đặc biệt",
				"custom_shift_group": shift_group,
			},
			update_modified=True,
		)

	return {
		"status": "COMPLETED",
		"effective_from": EFFECTIVE_FROM,
		"effective_to": EFFECTIVE_TO,
		"employees": len(results),
		"cancelled_auto_assignments": sum(row["cancelled_auto_assignments"] for row in results),
		"results": results,
	}


def verify_special_shift_rollout() -> dict:
	"""Verify masters, memberships and every planned day through year end."""
	_validate_dependencies(require_groups=True)
	mismatches = []
	assignment_total = 0
	for employee, (employee_name, shift_group) in SPECIAL_EMPLOYEES.items():
		_validate_employee(employee, employee_name)
		definition = SPECIAL_SHIFT_GROUPS[shift_group]
		group_differences = _compare_group(
			shift_group, definition, _schedule_rows(definition["schedule"])
		)
		if group_differences:
			mismatches.append(
				{"employee": employee, "issue": "GROUP_CONFLICT", "details": group_differences}
			)

		employee_row = frappe.db.get_value(
			"Employee",
			employee,
			["custom_working_schedule_type", "custom_shift_group"],
			as_dict=True,
		)
		if employee_row.custom_working_schedule_type != "Lịch đặc biệt" or employee_row.custom_shift_group != shift_group:
			mismatches.append(
				{
					"employee": employee,
					"issue": "EMPLOYEE_DISPLAY_FIELDS",
					"actual": employee_row,
				}
			)

		membership = frappe.get_all(
			"VNT Shift Group Assignment",
			filters={
				"employee": employee,
				"shift_group": shift_group,
				"from_date": EFFECTIVE_FROM,
				"to_date": EFFECTIVE_TO,
				"status": "Active",
			},
			pluck="name",
		)
		if len(membership) != 1:
			mismatches.append(
				{"employee": employee, "issue": "MEMBERSHIP_COUNT", "actual": len(membership)}
			)

		rows = frappe.get_all(
			"Shift Assignment",
			filters={
				"employee": employee,
				"start_date": ["between", [EFFECTIVE_FROM, EFFECTIVE_TO]],
				"docstatus": ["<", 2],
			},
			fields=[
				"name",
				"start_date",
				"end_date",
				"shift_type",
				"custom_shift_group",
				"custom_assignment_source",
				"custom_generated_by_shift_group",
			],
		)
		assignment_total += len(rows)
		by_date = {}
		for row in rows:
			by_date.setdefault(row.start_date, []).append(row)

		work_date = EFFECTIVE_FROM
		while work_date <= EFFECTIVE_TO:
			expected_shift = definition["schedule"][work_date.weekday()]
			actual_rows = by_date.get(work_date, [])
			if expected_shift is None:
				if actual_rows:
					mismatches.append(
						{
							"employee": employee,
							"date": work_date,
							"issue": "EXPECTED_OFF",
							"assignments": [row.name for row in actual_rows],
						}
					)
			elif len(actual_rows) != 1:
				mismatches.append(
					{
						"employee": employee,
						"date": work_date,
						"issue": "ASSIGNMENT_COUNT",
						"expected": 1,
						"actual": len(actual_rows),
					}
				)
			else:
				actual = actual_rows[0]
				if (
					actual.shift_type != expected_shift
					or actual.custom_shift_group != shift_group
					or not actual.custom_generated_by_shift_group
					or actual.custom_assignment_source != "Kíp tự động"
					or actual.start_date != actual.end_date
				):
					mismatches.append(
						{
							"employee": employee,
							"date": work_date,
							"issue": "ASSIGNMENT_VALUE",
							"expected_shift": expected_shift,
							"assignment": actual,
						}
					)
			work_date += timedelta(days=1)

	return {
		"status": "PASS" if not mismatches else "FAIL",
		"employees": len(SPECIAL_EMPLOYEES),
		"from_date": EFFECTIVE_FROM,
		"to_date": EFFECTIVE_TO,
		"non_cancelled_assignments": assignment_total,
		"mismatch_count": len(mismatches),
		"mismatches": mismatches[:100],
	}


def _request(employee, shift_group):
	return _validate_request(
		[employee],
		shift_group,
		EFFECTIVE_FROM,
		EFFECTIVE_TO,
		EFFECTIVE_TO,
		"Chuyển sang lịch đặc biệt theo bảng phân kíp HR, hiệu lực 14/10/2026.",
	)


def _validate_dependencies(*, require_groups=False):
	if not frappe.db.exists("Company", COMPANY):
		frappe.throw(_("Company does not exist: {0}").format(COMPANY))
	for shift_type in ("Sáng", "Chiều", "Đêm", "Hành chính"):
		if not frappe.db.exists("Shift Type", shift_type):
			frappe.throw(_("Shift Type does not exist: {0}").format(shift_type))
	for definition in SPECIAL_SHIFT_GROUPS.values():
		if not frappe.db.exists("Holiday List", definition["holiday_list"]):
			frappe.throw(_("Holiday List does not exist: {0}").format(definition["holiday_list"]))
	if require_groups:
		missing = [name for name in SPECIAL_SHIFT_GROUPS if not frappe.db.exists("VNT Shift Group", name)]
		if missing:
			frappe.throw(_("Special Shift Groups are missing: {0}").format(", ".join(missing)))


def _validate_employee(employee, expected_name):
	row = frappe.db.get_value("Employee", employee, ["employee_name", "company", "status"], as_dict=True)
	if not row:
		frappe.throw(_("Employee does not exist: {0}").format(employee))
	if row.employee_name != expected_name or row.company != COMPANY or row.status != "Active":
		frappe.throw(
			_("Employee identity/company/status differs for {0}; expected active {1} in {2}.").format(
				employee, expected_name, COMPANY
			)
		)


def _schedule_rows(schedule):
	return [
		{
			"day_of_week": weekday,
			"shift_type": shift_type,
			"is_off": 0 if shift_type else 1,
			"sequence": index,
		}
		for index, (weekday, shift_type) in enumerate(zip(WEEKDAYS, schedule, strict=True), start=1)
	]


def _compare_group(group_name, definition, expected_schedule):
	group = frappe.get_doc("VNT Shift Group", group_name)
	differences = []
	for fieldname, expected in (
		("company", COMPANY),
		("holiday_list", definition["holiday_list"]),
		("effective_from", EFFECTIVE_FROM),
		("effective_to", EFFECTIVE_TO),
	):
		value = group.get(fieldname)
		actual = getdate(value) if fieldname.startswith("effective_") and value else value
		if actual != expected:
			differences.append({"field": fieldname, "expected": expected, "actual": actual})
	actual_by_day = {row.day_of_week: row for row in group.schedule}
	for expected in expected_schedule:
		actual = actual_by_day.get(expected["day_of_week"])
		if not actual or actual.shift_type != expected["shift_type"] or bool(actual.is_off) != bool(expected["is_off"]):
			differences.append({"day": expected["day_of_week"], "expected": expected})
	return differences
