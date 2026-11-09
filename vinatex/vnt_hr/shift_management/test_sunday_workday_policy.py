from datetime import date
from unittest import TestCase

import frappe

from vinatex.vnt_hr.attendance_processing import classify_work_date
from vinatex.vnt_hr.shift_management.constants import AUTO_ASSIGNMENT_SOURCE
from vinatex.vnt_hr.shift_management.shift_assignment_service import (
	_plan_employee_date,
)


WORK_DATE = date(2026, 11, 1)
SATURDAY_DATE = date(2026, 10, 31)


def _employee(department):
	return frappe._dict(
		name="EMP-001",
		company="Nhà máy Sợi Vinatex Nam Định",
		department=department,
		holiday_list="2026",
	)


def _window(*, work_date=WORK_DATE, is_off=False):
	return frappe._dict(
		employee="EMP-001",
		work_date=work_date,
		is_off=is_off,
		shift_group=None,
		shift_type=None if is_off else "Hành chính",
		shift_doc=frappe._dict(holiday_list=None),
	)


def _holiday_context(*, weekly_off, work_date=WORK_DATE):
	return frappe._dict(
		company_lists={"Nhà máy Sợi Vinatex Nam Định": "2026"},
		holidays={
			"2026": {
				work_date: frappe._dict(
					holiday_date=work_date,
					weekly_off=weekly_off,
					description="Sunday" if weekly_off else "Public holiday",
				)
			}
		},
	)


def _planning_context(*, shift_group="HC", existing_assignment=None):
	return {
		"existing_assignments": (
			{("EMP-001", WORK_DATE): existing_assignment}
			if existing_assignment
			else {}
		),
		"memberships": {
			"EMP-001": [
				frappe._dict(
					name="MEMBERSHIP-001",
					shift_group=shift_group,
					from_date=date(2026, 1, 1),
					to_date=date(2026, 12, 31),
				)
			]
		},
		"groups": {
			shift_group: frappe._dict(
				name=shift_group,
				company="Nhà máy Sợi Vinatex Nam Định",
				disabled=0,
				effective_from=date(2026, 1, 1),
				effective_to=date(2026, 12, 31),
			)
		},
		"schedules": {
			(shift_group, "Sunday"): frappe._dict(
				parent=shift_group,
				day_of_week="Sunday",
				shift_type=None,
				is_off=1,
			)
		},
		"shift_types": {"Hành chính"},
	}


class TestSundayWorkdayPolicy(TestCase):
	def test_target_department_sunday_off_schedule_uses_default_shift(self):
		employee = _employee("Vào bông - NMSVNĐ")
		employee.update(
			employee_name="Lê Gia Huy",
			designation="Công nhân",
			default_shift="Hành chính",
			custom_shift_group="HC",
		)
		plan = _plan_employee_date(employee, WORK_DATE, _planning_context())
		self.assertEqual(plan["action"], "CREATE")
		self.assertEqual(plan["shift_type"], "Hành chính")
		self.assertEqual(plan["shift_group"], "HC")

	def test_target_department_weekly_off_is_work(self):
		for department in (
			"Vào bông - NMSVNĐ",
			"Công đoạn Đóng gói - NMSVNĐ",
		):
			with self.subTest(department=department):
				self.assertEqual(
					classify_work_date(
						_employee(department),
						_window(),
						_holiday_context(weekly_off=1),
					),
					"work",
				)

	def test_target_department_weekly_off_on_non_sunday_stays_off(self):
		self.assertEqual(
			classify_work_date(
				_employee("Vào bông - NMSVNĐ"),
				_window(work_date=SATURDAY_DATE),
				_holiday_context(weekly_off=1, work_date=SATURDAY_DATE),
			),
			"off",
		)

	def test_rotating_group_sunday_off_is_not_replaced_by_default_shift(self):
		employee = _employee("Vào bông - NMSVNĐ")
		employee.update(
			employee_name="Công nhân kíp",
			designation="Công nhân",
			default_shift="Hành chính",
			custom_shift_group="Kíp A",
		)
		plan = _plan_employee_date(
			employee,
			WORK_DATE,
			_planning_context(shift_group="Kíp A"),
		)
		self.assertEqual(plan["action"], "OFF")
		self.assertIsNone(plan["shift_type"])

	def test_policy_assignment_is_ignored_after_department_transfer(self):
		employee = _employee("Vào bông - NMSVNĐ")
		employee.update(
			employee_name="Lê Gia Huy",
			designation="Công nhân",
			default_shift="Hành chính",
			custom_shift_group="HC",
		)
		initial_plan = _plan_employee_date(
			employee, WORK_DATE, _planning_context()
		)
		self.assertEqual(initial_plan["action"], "CREATE")

		existing_assignment = frappe._dict(
			name="SHIFT-ASSIGNMENT-001",
			shift_type="Hành chính",
			custom_shift_group="HC",
			custom_assignment_source=AUTO_ASSIGNMENT_SOURCE,
			custom_generated_by_shift_group=1,
		)
		employee.department = "Sản xuất"
		refreshed_plan = _plan_employee_date(
			employee,
			WORK_DATE,
			_planning_context(existing_assignment=existing_assignment),
		)
		self.assertEqual(refreshed_plan["action"], "OFF")
		self.assertIsNone(refreshed_plan["shift_type"])

	def test_non_target_department_weekly_off_stays_off(self):
		self.assertEqual(
			classify_work_date(
				_employee("Sản xuất"),
				_window(),
				_holiday_context(weekly_off=1),
			),
			"off",
		)

	def test_target_department_public_holiday_stays_holiday(self):
		self.assertEqual(
			classify_work_date(
				_employee("Vào bông - NMSVNĐ"),
				_window(),
				_holiday_context(weekly_off=0),
			),
			"holiday",
		)

	def test_target_department_explicit_off_window_stays_off(self):
		self.assertEqual(
			classify_work_date(
				_employee("Vào bông - NMSVNĐ"),
				_window(is_off=True),
				_holiday_context(weekly_off=1),
			),
			"off",
		)

	def test_employee_moved_out_uses_current_department(self):
		employee = _employee("Vào bông - NMSVNĐ")
		self.assertEqual(
			classify_work_date(
				employee, _window(), _holiday_context(weekly_off=1)
			),
			"work",
		)
		employee.department = "Sản xuất"
		self.assertEqual(
			classify_work_date(
				employee, _window(), _holiday_context(weekly_off=1)
			),
			"off",
		)
