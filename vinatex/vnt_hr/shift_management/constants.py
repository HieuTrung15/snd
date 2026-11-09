"""Shared business constants for factory shift management.

Keep weekday and source mappings here so controllers, services, reports and tests
do not spread magic numbers or translated values throughout the app.
"""

from __future__ import annotations

from datetime import time

WEEKDAYS = (
	"Monday",
	"Tuesday",
	"Wednesday",
	"Thursday",
	"Friday",
	"Saturday",
	"Sunday",
)
WEEKDAY_SEQUENCE = {day: index for index, day in enumerate(WEEKDAYS, start=1)}

AUTO_ASSIGNMENT_SOURCE = "Kíp tự động"
ASSIGNMENT_SOURCES = (
	AUTO_ASSIGNMENT_SOURCE,
	"Phân ca thủ công",
	"Đổi ca",
	"Điều động",
	"Legacy",
	"Import",
)

WORKING_SCHEDULE_TYPES = (
	"Hành chính",
	"Theo kíp",
	"Ca cố định",
	"Lịch đặc biệt",
)

# Scheduler horizon is configured in one place and is intentionally not copied
# into controllers or reports.
DEFAULT_GENERATION_DAYS = 60
MAX_MANUAL_GENERATION_DAYS = 366
MAX_PREVIEW_ROWS = 2_000
MAX_BULK_TRANSFER_EMPLOYEES = 200
MAX_BACKDATED_TRANSFER_EMPLOYEES = 20
BACKDATED_TRANSFER_CONFIRMATION = "XÁC NHẬN HỒI TỐ"

SUNDAY_WORKDAY_DEPARTMENTS = frozenset(
	{
		"Vào bông - NMSVNĐ",
		"Công đoạn Đóng gói - NMSVNĐ",
	}
)
SUNDAY_WORKDAY_SHIFT_GROUP = "HC"

SHIFT_TIME_EXPECTATIONS = {
	"morning": (time(6, 0), time(14, 0)),
	"afternoon": (time(14, 0), time(22, 0)),
	"night": (time(22, 0), time(6, 0)),
	"administrative": (time(7, 30), time(16, 30)),
}

DEFAULT_SHIFT_TYPE_NAMES = {
	"morning": "Sáng",
	"afternoon": "Chiều",
	"night": "Đêm",
	"administrative": "Hành chính",
}

# The first implementation deliberately keeps the weekly matrix explicit so HR
# can audit it without understanding a cycle/phase abstraction.
DEFAULT_SHIFT_GROUP_MATRIX = {
	"Kíp 1": ("afternoon", "afternoon", "night", "night", None, "morning", "morning"),
	"Kíp 2": ("afternoon", "night", "night", None, "morning", "morning", "afternoon"),
	"Kíp 3": ("night", "night", None, "morning", "morning", "afternoon", "afternoon"),
	"Kíp 4": ("night", None, "morning", "morning", "afternoon", "afternoon", "night"),
	"Kíp 5": (None, "morning", "morning", "afternoon", "afternoon", "night", "night"),
	"Kíp 6": ("morning", "morning", "afternoon", "afternoon", "night", "night", None),
	"Kíp 7": ("morning", "afternoon", "afternoon", "night", "night", None, "morning"),
}

SHIFT_GROUP_WEEKLY_OFF = {
	group_name: WEEKDAYS[weekly_schedule.index(None)]
	for group_name, weekly_schedule in DEFAULT_SHIFT_GROUP_MATRIX.items()
}
