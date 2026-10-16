"""Explicit and idempotent setup helpers for factory shift masters."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import get_time, getdate, today

from vinatex.vnt_hr.shift_management.constants import (
	DEFAULT_SHIFT_GROUP_MATRIX,
	DEFAULT_SHIFT_TYPE_NAMES,
	SHIFT_TIME_EXPECTATIONS,
	WEEKDAYS,
)


@frappe.whitelist()
def inspect_shift_type_mapping(mapping=None) -> dict:
	"""Return exact matches/conflicts without modifying any Shift Type."""
	frappe.only_for(("HR Manager", "System Manager"))
	return _inspect_shift_type_mapping(frappe.parse_json(mapping) if mapping else None)


@frappe.whitelist()
def setup_default_shift_groups(
	company: str,
	effective_from=None,
	shift_type_mapping=None,
	create_missing_shift_types: bool = False,
) -> dict:
	"""Create only missing standard masters after an explicit privileged action.

	Existing Shift Types and Shift Groups are compared and reported but never
	updated, renamed or deleted. Holiday Lists are handled by a separate action.
	"""
	frappe.only_for(("HR Manager", "System Manager"))
	if not frappe.db.exists("Company", company):
		frappe.throw(_("Company {0} does not exist.").format(company))

	mapping = frappe.parse_json(shift_type_mapping) if shift_type_mapping else None
	inspection = _inspect_shift_type_mapping(mapping)
	if frappe.utils.cint(create_missing_shift_types):
		_create_explicitly_missing_shift_types(inspection)
		inspection = _inspect_shift_type_mapping(mapping)

	required_roles = ("morning", "afternoon", "night")
	missing_required = [role for role in required_roles if inspection[role]["status"] != "MATCH"]
	if missing_required:
		return {
			"status": "BLOCKED",
			"shift_types": inspection,
			"groups": [],
			"message": "Production Shift Type mapping has missing/conflicting entries; no group was created.",
		}

	resolved_mapping = {role: row["name"] for role, row in inspection.items() if row.get("name")}
	group_results = []
	for group_name, weekly_schedule in DEFAULT_SHIFT_GROUP_MATRIX.items():
		expected_schedule = [
			{
				"day_of_week": weekday,
				"shift_type": resolved_mapping.get(role) if role else None,
				"is_off": 0 if role else 1,
				"sequence": index,
			}
			for index, (weekday, role) in enumerate(zip(WEEKDAYS, weekly_schedule, strict=True), start=1)
		]
		if frappe.db.exists("VNT Shift Group", group_name):
			group_results.append(_compare_existing_group(group_name, company, expected_schedule))
			continue

		doc = frappe.get_doc(
			{
				"doctype": "VNT Shift Group",
				"shift_group_name": group_name,
				"company": company,
				"effective_from": getdate(effective_from or today()),
				"description": "Standard 7-crew factory rotation. Created by explicit setup action.",
				"schedule": expected_schedule,
			}
		)
		doc.insert(ignore_permissions=True)
		group_results.append({"shift_group": doc.name, "status": "CREATED", "differences": []})

	return {"status": "OK", "shift_types": inspection, "groups": group_results}


def _inspect_shift_type_mapping(mapping=None) -> dict:
	mapping = {**DEFAULT_SHIFT_TYPE_NAMES, **(mapping or {})}
	shift_types = frappe.get_all("Shift Type", fields=["name", "start_time", "end_time"])
	by_name = {row.name: row for row in shift_types}
	result = {}

	for role, expected_times in SHIFT_TIME_EXPECTATIONS.items():
		configured_name = mapping.get(role)
		configured = by_name.get(configured_name)
		if configured:
			actual_times = (get_time(configured.start_time), get_time(configured.end_time))
			if actual_times == expected_times:
				result[role] = {"status": "MATCH", "name": configured.name, "expected": expected_times}
			else:
				result[role] = {
					"status": "CONFLICT",
					"name": configured.name,
					"expected": expected_times,
					"actual": actual_times,
					"message": "Existing Shift Type was not changed.",
				}
			continue

		time_matches = [
			row for row in shift_types if (get_time(row.start_time), get_time(row.end_time)) == expected_times
		]
		if len(time_matches) == 1:
			result[role] = {
				"status": "MATCH",
				"name": time_matches[0].name,
				"expected": expected_times,
				"message": f"Reused existing Shift Type with a different name: {time_matches[0].name}",
			}
		elif len(time_matches) > 1:
			result[role] = {
				"status": "AMBIGUOUS",
				"name": None,
				"expected": expected_times,
				"candidates": [row.name for row in time_matches],
			}
		else:
			result[role] = {
				"status": "MISSING",
				"name": configured_name,
				"expected": expected_times,
			}
	return result


def _create_explicitly_missing_shift_types(inspection):
	for role, row in inspection.items():
		if row["status"] != "MISSING":
			continue
		start_time, end_time = SHIFT_TIME_EXPECTATIONS[role]
		frappe.get_doc(
			{
				"doctype": "Shift Type",
				"name": row["name"],
				"start_time": start_time,
				"end_time": end_time,
				"enable_auto_attendance": 0,
			}
		).insert(ignore_permissions=True)


def _compare_existing_group(group_name, company, expected_schedule):
	group = frappe.get_doc("VNT Shift Group", group_name)
	differences = []
	if group.company != company:
		differences.append({"field": "company", "expected": company, "actual": group.company})
	actual_by_day = {row.day_of_week: row for row in group.schedule}
	for expected in expected_schedule:
		actual = actual_by_day.get(expected["day_of_week"])
		if not actual:
			differences.append({"day": expected["day_of_week"], "issue": "MISSING"})
			continue
		if bool(actual.is_off) != bool(expected["is_off"]) or actual.shift_type != expected["shift_type"]:
			differences.append(
				{
					"day": expected["day_of_week"],
					"expected_shift": expected["shift_type"],
					"expected_off": bool(expected["is_off"]),
					"actual_shift": actual.shift_type,
					"actual_off": bool(actual.is_off),
				}
			)
	return {
		"shift_group": group_name,
		"status": "MATCH" if not differences else "CONFLICT",
		"differences": differences,
		"message": None if not differences else "Existing Shift Group was not changed.",
	}
