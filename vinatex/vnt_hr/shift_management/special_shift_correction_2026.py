"""Idempotent correction of the 2026 special weekly shifts (HR table, 20/10/2026).

* Every special Shift Group master is valid for the whole year 2026.
* Lại Văn Hiệp moves from the incorrect "ĐB HC-Đêm - Nghỉ T6" master to the
  approved "ĐB HC-Đêm - Nghỉ T7" schedule.
* Bùi Ngọc An and Nguyễn Hải Đăng receive their first special schedule.

Memberships cannot be backdated (the employees already have check-ins today), so
they start on ``EFFECTIVE_FROM`` and the previous plan is kept as history.

    bench --site <site> execute vinatex.vnt_hr.shift_management.special_shift_correction_2026.setup_groups
    bench --site <site> execute vinatex.vnt_hr.shift_management.special_shift_correction_2026.preview
    bench --site <site> execute vinatex.vnt_hr.shift_management.special_shift_correction_2026.execute
    bench --site <site> execute vinatex.vnt_hr.shift_management.special_shift_correction_2026.verify
"""

from __future__ import annotations

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import getdate

from vinatex.vnt_hr.shift_management import special_shift_rollout as rollout
from vinatex.vnt_hr.shift_management.constants import AUTO_ASSIGNMENT_SOURCE
from vinatex.vnt_hr.shift_management.shift_group_transfer_service import (
	_build_preview,
	_run_bulk_shift_group_transfer,
	_validate_request,
)

COMPANY = rollout.COMPANY
GROUP_EFFECTIVE_FROM = rollout.GROUP_EFFECTIVE_FROM
GROUP_EFFECTIVE_TO = rollout.EFFECTIVE_TO
EFFECTIVE_FROM = rollout.CORRECTION_EFFECTIVE_FROM
EFFECTIVE_TO = rollout.EFFECTIVE_TO
DESCRIPTION = "Lịch đặc biệt 2026 theo bảng phân kíp HR cập nhật ngày 20/10/2026."

# Monday .. Sunday; None = OFF. Holiday List follows the KIP list with the same weekly off.
NEW_SHIFT_GROUPS = {
	"ĐB HC-Đêm - Nghỉ T7": {
		"holiday_list": "KIP-07-2026",
		"schedule": ("Hành chính", "Hành chính", "Hành chính", "Đêm", "Đêm", None, "Hành chính"),
	},
	"ĐB Điện - Nghỉ T5": {
		"holiday_list": "KIP-02-2026",
		"schedule": ("Hành chính", "Hành chính", "Đêm", None, "Chiều", "Sáng", "Chiều"),
	},
	"ĐB Điện - Nghỉ CN": {
		"holiday_list": "KIP-06-2026",
		"schedule": ("Chiều", "Đêm", "Chiều", "Hành chính", "Hành chính", "Hành chính", None),
	},
}

TRANSFERS = {
	"NMSVNĐ00159": ("Lại Văn Hiệp", "ĐB HC-Đêm - Nghỉ T7"),
	"NMSVNĐ00164": ("Bùi Ngọc An", "ĐB Điện - Nghỉ T5"),
	"NMSVNĐ00168": ("Nguyễn Hải Đăng", "ĐB Điện - Nghỉ CN"),
}

SUPERSEDED_GROUP = "ĐB HC-Đêm - Nghỉ T6"


def setup_groups() -> dict:
	"""Create the missing masters and widen every special master to the whole year."""
	_validate_dependencies()
	results = []
	for group_name, definition in NEW_SHIFT_GROUPS.items():
		expected_schedule = rollout._schedule_rows(definition["schedule"])
		if frappe.db.exists("VNT Shift Group", group_name):
			differences = _compare_group(group_name, definition)
			if differences:
				frappe.throw(
					_("Special Shift Group {0} already exists with conflicts: {1}").format(
						group_name, differences
					)
				)
			results.append({"shift_group": group_name, "status": "MATCH"})
			continue

		frappe.get_doc(
			{
				"doctype": "VNT Shift Group",
				"shift_group_name": group_name,
				"company": COMPANY,
				"holiday_list": definition["holiday_list"],
				"effective_from": GROUP_EFFECTIVE_FROM,
				"effective_to": GROUP_EFFECTIVE_TO,
				"description": DESCRIPTION,
				"schedule": expected_schedule,
			}
		).insert(ignore_permissions=True)
		results.append({"shift_group": group_name, "status": "CREATED"})

	# Widening the validity window does not reinterpret any generated day, so it
	# is written directly instead of through the "used schedule" guard.
	for group_name in rollout.SPECIAL_SHIFT_GROUPS:
		values = frappe.db.get_value(
			"VNT Shift Group", group_name, ["effective_from", "effective_to"], as_dict=True
		)
		if getdate(values.effective_from) != GROUP_EFFECTIVE_FROM or getdate(values.effective_to) != GROUP_EFFECTIVE_TO:
			frappe.db.set_value(
				"VNT Shift Group",
				group_name,
				{"effective_from": GROUP_EFFECTIVE_FROM, "effective_to": GROUP_EFFECTIVE_TO},
			)
			results.append({"shift_group": group_name, "status": "PERIOD_WIDENED"})

	superseded_note = f"Không dùng từ {EFFECTIVE_FROM:%d/%m/%Y}: thay bằng kíp ĐB HC-Đêm - Nghỉ T7."
	description = frappe.db.get_value("VNT Shift Group", SUPERSEDED_GROUP, "description") or ""
	if superseded_note not in description:
		frappe.db.set_value(
			"VNT Shift Group", SUPERSEDED_GROUP, "description", f"{description}\n{superseded_note}".strip()
		)

	return {"status": "OK", "groups": results}


def preview() -> dict:
	_validate_dependencies(require_groups=True)
	previews = []
	for employee, (employee_name, shift_group) in TRANSFERS.items():
		rollout._validate_employee(employee, employee_name)
		item = _build_preview(_request(employee, shift_group))
		item.pop("assignment_names_to_cancel", None)
		previews.append(item)
	return {
		"status": "READY" if all(item["counts"].get("BLOCKED", 0) == 0 for item in previews) else "BLOCKED",
		"effective_from": EFFECTIVE_FROM,
		"effective_to": EFFECTIVE_TO,
		"previews": previews,
	}


def execute() -> dict:
	result = preview()
	if result["status"] != "READY":
		frappe.throw(_("Special shift correction preview is blocked; nothing was changed."))

	results = []
	for employee, (employee_name, shift_group) in TRANSFERS.items():
		transfer = _run_bulk_shift_group_transfer(_request(employee, shift_group), requested_by=frappe.session.user)
		frappe.db.set_value(
			"Employee",
			employee,
			{"custom_working_schedule_type": "Lịch đặc biệt", "custom_shift_group": shift_group},
			update_modified=True,
		)
		results.append({"employee": employee, "employee_name": employee_name, **transfer})
	return {"status": "COMPLETED", "results": results}


def verify() -> dict:
	"""Check masters, memberships and every planned day of the corrected period."""
	_validate_dependencies(require_groups=True)
	mismatches = []
	for group_name, definition in NEW_SHIFT_GROUPS.items():
		differences = _compare_group(group_name, definition)
		if differences:
			mismatches.append({"shift_group": group_name, "issue": "GROUP_CONFLICT", "details": differences})
	for group_name in rollout.SPECIAL_SHIFT_GROUPS:
		values = frappe.db.get_value("VNT Shift Group", group_name, ["effective_from", "effective_to"], as_dict=True)
		if getdate(values.effective_from) != GROUP_EFFECTIVE_FROM or getdate(values.effective_to) != GROUP_EFFECTIVE_TO:
			mismatches.append({"shift_group": group_name, "issue": "GROUP_PERIOD", "actual": values})

	for employee, (employee_name, shift_group) in TRANSFERS.items():
		rollout._validate_employee(employee, employee_name)
		employee_row = frappe.db.get_value(
			"Employee", employee, ["custom_working_schedule_type", "custom_shift_group"], as_dict=True
		)
		if employee_row.custom_working_schedule_type != "Lịch đặc biệt" or employee_row.custom_shift_group != shift_group:
			mismatches.append({"employee": employee, "issue": "EMPLOYEE_DISPLAY_FIELDS", "actual": employee_row})

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
			mismatches.append({"employee": employee, "issue": "MEMBERSHIP_COUNT", "actual": len(membership)})

		mismatches.extend(_verify_days(employee, shift_group, NEW_SHIFT_GROUPS[shift_group]["schedule"]))

	return {
		"status": "PASS" if not mismatches else "FAIL",
		"from_date": EFFECTIVE_FROM,
		"to_date": EFFECTIVE_TO,
		"mismatch_count": len(mismatches),
		"mismatches": mismatches[:100],
	}


def _verify_days(employee, shift_group, schedule):
	rows = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": employee,
			"start_date": ["between", [EFFECTIVE_FROM, EFFECTIVE_TO]],
			"docstatus": 1,
			"status": "Active",
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
	by_date = {}
	for row in rows:
		by_date.setdefault(row.start_date, []).append(row)

	mismatches = []
	work_date = EFFECTIVE_FROM
	while work_date <= EFFECTIVE_TO:
		expected_shift = schedule[work_date.weekday()]
		actual_rows = by_date.get(work_date, [])
		if expected_shift is None:
			if actual_rows:
				mismatches.append({"employee": employee, "date": work_date, "issue": "EXPECTED_OFF"})
		elif len(actual_rows) != 1:
			mismatches.append(
				{"employee": employee, "date": work_date, "issue": "ASSIGNMENT_COUNT", "actual": len(actual_rows)}
			)
		else:
			actual = actual_rows[0]
			if (
				actual.shift_type != expected_shift
				or actual.custom_shift_group != shift_group
				or not actual.custom_generated_by_shift_group
				or actual.custom_assignment_source != AUTO_ASSIGNMENT_SOURCE
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
	return mismatches


def _request(employee, shift_group):
	return _validate_request(
		[employee],
		shift_group,
		EFFECTIVE_FROM,
		EFFECTIVE_TO,
		EFFECTIVE_TO,
		f"Áp dụng lịch đặc biệt theo bảng phân kíp HR, hiệu lực {EFFECTIVE_FROM:%d/%m/%Y}.",
	)


def _compare_group(group_name, definition):
	return rollout._compare_group(
		group_name,
		definition,
		rollout._schedule_rows(definition["schedule"]),
	)


def _validate_dependencies(*, require_groups=False):
	rollout._validate_dependencies()
	for definition in NEW_SHIFT_GROUPS.values():
		if not frappe.db.exists("Holiday List", definition["holiday_list"]):
			frappe.throw(_("Holiday List does not exist: {0}").format(definition["holiday_list"]))
	if require_groups:
		missing = [name for name in NEW_SHIFT_GROUPS if not frappe.db.exists("VNT Shift Group", name)]
		if missing:
			frappe.throw(_("Special Shift Groups are missing: {0}").format(", ".join(missing)))
