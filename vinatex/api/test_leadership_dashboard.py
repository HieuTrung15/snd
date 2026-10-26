from unittest import TestCase
from unittest.mock import patch

from frappe.utils import getdate

from vinatex.api.leadership_dashboard import _employee_scope_conditions


class TestLeadershipDashboard(TestCase):
	@patch("vinatex.api.leadership_dashboard.today", return_value="2026-10-23")
	def test_current_scope_only_includes_active_employees(self, _mock_today):
		conditions, _params = _employee_scope_conditions(
			getdate("2026-10-23"), "Nhà máy Sợi Vinatex Nam Định", ()
		)

		self.assertIn("e.status = 'Active'", conditions)

	@patch("vinatex.api.leadership_dashboard.today", return_value="2026-10-23")
	def test_historical_scope_still_only_includes_active_employees(self, _mock_today):
		conditions, _params = _employee_scope_conditions(
			getdate("2026-10-22"), "Nhà máy Sợi Vinatex Nam Định", ()
		)

		self.assertIn("e.status = 'Active'", conditions)
		self.assertIn("e.date_of_joining <= %(as_of_date)s", conditions)
		self.assertIn(
			"(e.relieving_date IS NULL OR e.relieving_date > %(as_of_date)s)",
			conditions,
		)
