"""Unified entry points for effective-dated Shift Group transfers."""

from __future__ import annotations

import frappe
from frappe.utils import getdate, today

from vinatex.vnt_hr.shift_management.backdated_shift_group_transfer_service import (
	execute_backdated_shift_group_transfer,
	preview_backdated_shift_group_transfer,
)
from vinatex.vnt_hr.shift_management.current_shift_group_sync import (
	get_required_hc_holiday_list,
)
from vinatex.vnt_hr.shift_management.shift_group_transfer_service import (
	execute_bulk_shift_group_transfer,
	preview_bulk_shift_group_transfer,
)


@frappe.whitelist()
def preview_shift_group_transfer(
	employees,
	target_shift_group,
	effective_date,
	membership_end_date,
	generate_until=None,
	note=None,
) -> dict:
	"""Preview with the server-selected normal or backdated engine."""
	get_required_hc_holiday_list(target_shift_group)
	request = _request_args(
		employees,
		target_shift_group,
		effective_date,
		membership_end_date,
		generate_until,
		note,
	)
	mode = _mode_for(effective_date)
	if mode == "BACKDATED":
		result = preview_backdated_shift_group_transfer(**request)
	else:
		result = preview_bulk_shift_group_transfer(**request)
	return _with_common_result_fields(result, mode, target_shift_group, effective_date)


@frappe.whitelist()
def execute_shift_group_transfer(
	employees,
	target_shift_group,
	effective_date,
	membership_end_date,
	generate_until=None,
	note=None,
	preview_token=None,
	confirmation_text=None,
) -> dict:
	"""Execute with the server-selected normal or backdated engine."""
	get_required_hc_holiday_list(target_shift_group)
	request = _request_args(
		employees,
		target_shift_group,
		effective_date,
		membership_end_date,
		generate_until,
		note,
	)
	mode = _mode_for(effective_date)
	if mode == "BACKDATED":
		result = execute_backdated_shift_group_transfer(
			**request,
			preview_token=preview_token,
			confirmation_text=confirmation_text,
		)
	else:
		result = execute_bulk_shift_group_transfer(**request)
	return _with_common_result_fields(result, mode, target_shift_group, effective_date)


def _mode_for(effective_date) -> str:
	return "BACKDATED" if getdate(effective_date) < getdate(today()) else "NORMAL"


def _request_args(
	employees,
	target_shift_group,
	effective_date,
	membership_end_date,
	generate_until,
	note,
) -> dict:
	return {
		"employees": employees,
		"target_shift_group": target_shift_group,
		"effective_date": effective_date,
		"membership_end_date": membership_end_date,
		"generate_until": generate_until,
		"note": note,
	}


def _with_common_result_fields(result, mode, target_shift_group, effective_date) -> dict:
	result = dict(result or {})
	result["mode"] = mode
	result["target_shift_group"] = str(target_shift_group or "")
	result["effective_date"] = getdate(effective_date).isoformat()
	if "employees" not in result:
		result["employees"] = len(result.get("rows") or [])
	return result
