from unittest import TestCase
from unittest.mock import patch

import frappe

from vinatex.api.hr_dashboard import get_hr_dashboard_snapshot


class TestHrDashboard(TestCase):
	@patch("vinatex.api.hr_dashboard.frappe")
	@patch("vinatex.api.hr_dashboard.today", return_value="2026-10-18")
	def test_snapshot_groups_employees_by_workforce_structure(self, _mock_today, mock_frappe):
		mock_frappe.has_permission.return_value = True
		mock_frappe.db.count.return_value = 0
		mock_frappe.db.sql.side_effect = [
			[
				frappe._dict(
					designation="Công nhân đi ca",
					custom_designation_group=None,
					department="Phân xưởng Sợi",
					employment_type="HĐLĐ",
					branch="Nhà máy",
					gender="Female",
					age=30,
					seniority_months=24,
				),
				frappe._dict(
					designation="Công nhân đi ca",
					custom_designation_group="Công nhân",
					department="Phân xưởng Sợi",
					employment_type="HĐLĐ",
					branch="Nhà máy",
					gender="Male",
					age=31,
					seniority_months=36,
				),
				frappe._dict(
					designation="Trưởng ca",
					custom_designation_group="Quản lý cấp trung",
					department="Phòng Kỹ thuật",
					employment_type="HĐLĐ",
					branch="Nhà máy",
					gender="Male",
					age=40,
					seniority_months=60,
				),
				frappe._dict(
					designation=None,
					custom_designation_group=None,
					department="Phòng Kỹ thuật",
					employment_type="HĐLĐ",
					branch="Nhà máy",
					gender="Male",
					age=41,
					seniority_months=72,
				),
				frappe._dict(
					designation="   ",
					custom_designation_group="   ",
					department=None,
					employment_type="HĐLĐ",
					branch="Nhà máy",
					gender="Female",
					age=42,
					seniority_months=84,
				),
			],
			[],
		]

		result = get_hr_dashboard_snapshot.__wrapped__(as_of_date="2026-10-18")

		self.assertEqual(
			result["dimensions"]["designation"],
			{
				"labels": ["Công nhân đi ca", "Trưởng ca", "Chưa xác định"],
				"datasets": [{"name": "Nhân sự", "values": [2, 1, 2]}],
			},
		)
		self.assertEqual(
			result["dimensions"]["designation_group"],
			{
				"labels": ["Công nhân", "Quản lý cấp trung", "Chưa xác định"],
				"datasets": [{"name": "Nhân sự", "values": [2, 1, 2]}],
			},
		)
		self.assertEqual(
			result["dimensions"]["department"],
			{
				"labels": ["Phân xưởng Sợi", "Phòng Kỹ thuật", "Chưa xác định"],
				"datasets": [{"name": "Nhân sự", "values": [2, 2, 1]}],
			},
		)
		employee_query = mock_frappe.db.sql.call_args_list[0].args[0]
		self.assertIn("e.designation,", employee_query)
		self.assertIn("e.custom_designation_group,", employee_query)
		self.assertIn("AS department,", employee_query)
		self.assertIn("LEFT JOIN `tabDepartment`", employee_query)
