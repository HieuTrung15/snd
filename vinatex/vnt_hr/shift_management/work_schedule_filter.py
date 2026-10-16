"""Shared classification for attendance report work-schedule filters."""

from __future__ import annotations

from vinatex.vnt_hr.shift_management.constants import DEFAULT_SHIFT_GROUP_MATRIX


ADMINISTRATIVE_FILTER = "Ca Hành chính"
SHIFT_FILTER = "Theo kíp"
SPECIAL_SHIFT_FILTER = "Kíp đặc biệt"
WORK_SCHEDULE_FILTERS = (
	ADMINISTRATIVE_FILTER,
	SHIFT_FILTER,
	SPECIAL_SHIFT_FILTER,
)

_EXPLICIT_TYPE_TO_FILTER = {
	"Hành chính": ADMINISTRATIVE_FILTER,
	"Theo kíp": SHIFT_FILTER,
	"Lịch đặc biệt": SPECIAL_SHIFT_FILTER,
}
_STANDARD_SHIFT_GROUPS = frozenset(DEFAULT_SHIFT_GROUP_MATRIX)


def get_work_schedule_filter_value(employee) -> str:
	"""Classify an Employee into one of the three report filter values.

	The normalized Employee field wins. Legacy fields are used only when the
	normalized type is empty, so special-shift employees retaining an old
	``default_shift = Hành chính`` are not incorrectly classified as office staff.
	"""
	schedule_type = (employee.get("custom_working_schedule_type") or "").strip()
	if schedule_type:
		return _EXPLICIT_TYPE_TO_FILTER.get(schedule_type, "")

	shift_group = (employee.get("custom_shift_group") or "").strip()
	if shift_group:
		return SHIFT_FILTER if shift_group in _STANDARD_SHIFT_GROUPS else SPECIAL_SHIFT_FILTER

	default_shift = (employee.get("default_shift") or "").strip()
	if default_shift == "Hành chính":
		return ADMINISTRATIVE_FILTER
	if default_shift in _STANDARD_SHIFT_GROUPS:
		return SHIFT_FILTER
	return ""


def matches_work_schedule_filter(employee, selected_filter) -> bool:
	selected_filter = (selected_filter or "").strip()
	return not selected_filter or get_work_schedule_filter_value(employee) == selected_filter
