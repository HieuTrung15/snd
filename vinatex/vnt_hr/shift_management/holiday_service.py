"""Explicit, non-destructive Holiday List integration for rotating shift groups."""

from __future__ import annotations

import re
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import cint, getdate

from vinatex.vnt_hr.shift_management.constants import WEEKDAYS


@frappe.whitelist()
def preview_shift_group_holiday_list(shift_group: str, year: int) -> dict:
	"""Compare the expected weekly OFF dates with a linked/canonical list."""
	_require_holiday_sync_role()
	return _inspect_shift_group_holiday_list(shift_group, cint(year))


@frappe.whitelist()
def sync_shift_group_holiday_list(shift_group: str, year: int) -> dict:
	"""Create/link a matching list, but never overwrite an existing Holiday List.

	This is an explicit HR action. It does not update Employee, Company or Shift
	Type, and it does not merge statutory holidays into the Kíp weekly-off list.
	"""
	_require_holiday_sync_role()
	year = cint(year)
	inspection = _inspect_shift_group_holiday_list(shift_group, year)
	if inspection["status"] == "CONFLICT":
		return inspection

	group = frappe.get_doc("VNT Shift Group", shift_group)
	if inspection["status"] == "MATCH":
		if not group.holiday_list:
			group.holiday_list = inspection["holiday_list"]
			group.save(ignore_permissions=True)
			inspection["group_linked"] = True
		return inspection

	list_name = inspection["holiday_list"]
	holiday_doc = frappe.get_doc(
		{
			"doctype": "Holiday List",
			"holiday_list_name": list_name,
			"from_date": date(year, 1, 1),
			"to_date": date(year, 12, 31),
			"weekly_off": inspection["weekly_off"],
		}
	)
	for holiday_date in inspection["expected_dates"]:
		holiday_doc.append(
			"holidays",
			{
				"holiday_date": holiday_date,
				"description": inspection["weekly_off"],
				"weekly_off": 1,
			},
		)

	holiday_doc.insert(ignore_permissions=True)

	group.holiday_list = holiday_doc.name
	group.save(ignore_permissions=True)
	inspection.update(status="CREATED", holiday_list=holiday_doc.name, group_linked=True)
	return inspection


def _inspect_shift_group_holiday_list(shift_group: str, year: int) -> dict:
	_validate_year(year)
	group = frappe.get_doc("VNT Shift Group", shift_group)
	off_days = [row.day_of_week for row in group.schedule if row.is_off]
	if len(off_days) != 1:
		frappe.throw(_("Shift Group must have exactly one weekly OFF day before Holiday List sync."))

	weekly_off = off_days[0]
	expected_dates = _weekly_dates_for_year(year, weekly_off)
	list_name = _holiday_list_name(group.name, year)
	previous_holiday_list = group.holiday_list
	if group.holiday_list:
		linked_period = frappe.db.get_value(
			"Holiday List", group.holiday_list, ["from_date", "to_date"], as_dict=True
		)
		if linked_period and (
			getdate(linked_period.from_date) == date(year, 1, 1)
			and getdate(linked_period.to_date) == date(year, 12, 31)
		):
			list_name = group.holiday_list
	if not frappe.db.exists("Holiday List", list_name):
		return {
			"status": "MISSING",
			"shift_group": group.name,
			"holiday_list": list_name,
			"weekly_off": weekly_off,
			"expected_dates": expected_dates,
			"missing_dates": expected_dates,
			"unexpected_dates": [],
			"group_linked": False,
			"previous_holiday_list": previous_holiday_list,
		}

	holiday_list = frappe.db.get_value(
		"Holiday List", list_name, ["from_date", "to_date", "weekly_off"], as_dict=True
	)
	actual_rows = frappe.get_all(
		"Holiday",
		filters={"parent": list_name},
		fields=["holiday_date", "weekly_off"],
	)
	actual_dates = {getdate(row.holiday_date) for row in actual_rows}
	expected_set = set(expected_dates)
	missing = sorted(expected_set - actual_dates)
	unexpected = sorted(actual_dates - expected_set)
	metadata_matches = bool(
		getdate(holiday_list.from_date) == date(year, 1, 1)
		and getdate(holiday_list.to_date) == date(year, 12, 31)
		and holiday_list.weekly_off == weekly_off
		and all(cint(row.weekly_off) for row in actual_rows)
	)
	return {
		"status": "MATCH" if metadata_matches and not missing and not unexpected else "CONFLICT",
		"shift_group": group.name,
		"holiday_list": list_name,
		"weekly_off": weekly_off,
		"expected_dates": expected_dates,
		"missing_dates": missing,
		"unexpected_dates": unexpected,
		"metadata_matches": metadata_matches,
		"group_linked": group.holiday_list == list_name,
		"previous_holiday_list": previous_holiday_list,
		"message": None
		if metadata_matches and not missing and not unexpected
		else "Existing Holiday List differs; it was not changed.",
	}


def _weekly_dates_for_year(year: int, weekday: str) -> list[date]:
	weekday_index = WEEKDAYS.index(weekday)
	current = date(year, 1, 1)
	current += timedelta(days=(weekday_index - current.weekday()) % 7)
	dates = []
	while current.year == year:
		dates.append(current)
		current += timedelta(days=7)
	return dates


def _holiday_list_name(shift_group: str, year: int) -> str:
	match = re.search(r"(\d+)$", shift_group.strip())
	if match:
		return f"KIP-{int(match.group(1)):02d}-{year}"
	clean_name = re.sub(r"[^A-Z0-9]+", "-", shift_group.upper()).strip("-")
	return f"{clean_name}-{year}"


def _validate_year(year: int):
	if year < 2000 or year > 2100:
		frappe.throw(_("Year must be between 2000 and 2100."))


def _require_holiday_sync_role():
	frappe.only_for(("HR Manager", "System Manager"))
