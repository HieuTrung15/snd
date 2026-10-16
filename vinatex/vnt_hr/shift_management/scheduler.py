"""Scheduled entry points for factory shift assignment generation."""

from __future__ import annotations

import frappe
from frappe.utils import add_days, today

from vinatex.vnt_hr.shift_management.constants import DEFAULT_GENERATION_DAYS
from vinatex.vnt_hr.shift_management.shift_assignment_service import generate_shift_assignments
from vinatex.vnt_hr.shift_management.shift_group_service import shift_management_schema_is_ready


def run_daily_shift_assignment_generation():
	"""Maintain planned Shift Assignments from today through the look-ahead horizon."""
	if not shift_management_schema_is_ready():
		return {"status": "SKIPPED", "message": "Shift management schema is not installed."}

	result = generate_shift_assignments(
		today(),
		add_days(today(), DEFAULT_GENERATION_DAYS),
		preview=False,
	)
	frappe.logger("vnt_shift_management", allow_site=True, file_count=10).info(
		"Daily shift assignment generation completed: counts=%s diagnostics=%s",
		result.get("counts"),
		result.get("diagnostics"),
	)
	return result
