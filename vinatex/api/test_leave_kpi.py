# Copyright (c) 2026, vinatex and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from vinatex.api.leave_kpi import (
	ANNUAL_LEAVE_TYPE,
	_extract_remaining_annual_leave,
	get_employee_remaining_annual_leave,
	get_my_remaining_annual_leave,
)


class TestLeaveKpi(FrappeTestCase):
	def test_extract_remaining_annual_leave_sums_current_and_carried_leave_in_q1(self):
		leave_allocation = {
			"Nghỉ phép năm (2025)": {"remaining_leaves": 2},
			"Nghỉ phép năm (2026)": {"remaining_leaves": 12},
			"Công tác": {"remaining_leaves": 99},
		}

		self.assertEqual(_extract_remaining_annual_leave(leave_allocation), 14)

	def test_extract_remaining_annual_leave_keeps_current_year_intact_after_q1_if_carry_forward_covers_usage(self):
		leave_allocation = {
			"Nghỉ phép năm (2026)": {"remaining_leaves": 12},
		}

		self.assertEqual(_extract_remaining_annual_leave(leave_allocation), 12)

	def test_extract_remaining_annual_leave_reflects_current_year_deduction_after_carry_forward_is_exhausted(self):
		leave_allocation = {
			"Nghỉ phép năm (2026)": {"remaining_leaves": 10},
		}

		self.assertEqual(_extract_remaining_annual_leave(leave_allocation), 10)

	def test_get_employee_remaining_annual_leave_returns_zero_with_empty_employee(self):
		result = get_employee_remaining_annual_leave("", "2026-04-01", ANNUAL_LEAVE_TYPE)

		self.assertIsNone(result["employee"])
		self.assertEqual(result["leave_type"], ANNUAL_LEAVE_TYPE)
		self.assertEqual(result["remaining"], 0)
		self.assertEqual(result["as_of_date"], "2026-04-01")

	@patch("vinatex.api.leave_kpi.get_leave_details_with_year")
	def test_get_employee_remaining_annual_leave_uses_dashboard_logic_output(self, mock_leave_details):
		mock_leave_details.return_value = {
			"leave_allocation": {
				"Nghỉ phép năm (2026)": {"remaining_leaves": 10},
				"Công tác": {"remaining_leaves": 3},
			}
		}

		result = get_employee_remaining_annual_leave("EMP-0001", "2026-04-01", ANNUAL_LEAVE_TYPE)

		self.assertEqual(result["employee"], "EMP-0001")
		self.assertEqual(result["leave_type"], ANNUAL_LEAVE_TYPE)
		self.assertEqual(result["remaining"], 10)
		self.assertEqual(result["as_of_date"], "2026-04-01")
		mock_leave_details.assert_called_once_with("EMP-0001", frappe.utils.getdate("2026-04-01"), frappe.utils.getdate("2026-04-01"))

	@patch("vinatex.api.leave_kpi._get_active_employee_for_user")
	def test_get_my_remaining_annual_leave_returns_zero_without_active_employee(self, mock_employee):
		mock_employee.return_value = None

		result = get_my_remaining_annual_leave("2026-04-01")

		self.assertIsNone(result["employee"])
		self.assertIsNone(result["employee_name"])
		self.assertEqual(result["leave_type"], ANNUAL_LEAVE_TYPE)
		self.assertEqual(result["remaining"], 0)
		self.assertEqual(result["as_of_date"], "2026-04-01")

	@patch("vinatex.api.leave_kpi.get_employee_remaining_annual_leave")
	@patch("vinatex.api.leave_kpi._get_active_employee_for_user")
	def test_get_my_remaining_annual_leave_returns_current_user_balance(self, mock_employee, mock_balance):
		mock_employee.return_value = frappe._dict({"name": "EMP-0001", "employee_name": "Nguyen Van A"})
		mock_balance.return_value = {
			"employee": "EMP-0001",
			"leave_type": ANNUAL_LEAVE_TYPE,
			"remaining": 8,
			"as_of_date": "2026-04-01",
		}

		result = get_my_remaining_annual_leave("2026-04-01")

		self.assertEqual(result["employee"], "EMP-0001")
		self.assertEqual(result["employee_name"], "Nguyen Van A")
		self.assertEqual(result["remaining"], 8)
		mock_balance.assert_called_once_with("EMP-0001", frappe.utils.getdate("2026-04-01"), ANNUAL_LEAVE_TYPE)
