from unittest import TestCase
from unittest.mock import patch

import frappe

from vinatex.vnt_hr.shift_management import shift_group_transfer_workflow as workflow


_preview = workflow.preview_shift_group_transfer.__wrapped__
_execute = workflow.execute_shift_group_transfer.__wrapped__


def _request(effective_date="2026-11-01"):
	return {
		"employees": ["EMP-001"],
		"target_shift_group": "3",
		"effective_date": effective_date,
		"membership_end_date": "2026-12-31",
		"generate_until": "2026-12-31",
		"note": "Approved transfer",
	}


class TestShiftGroupTransferWorkflow(TestCase):
	@patch(
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.today",
		return_value="2026-11-05",
	)
	def test_preview_validates_hc_holiday_list_before_routing(self, _today):
		with patch.object(
			workflow,
			"get_required_hc_holiday_list",
			side_effect=frappe.ValidationError("HC Holiday List is required"),
			create=True,
		), patch.object(
			workflow, "preview_bulk_shift_group_transfer"
		) as preview_normal, patch.object(
			workflow, "preview_backdated_shift_group_transfer"
		) as preview_backdated:
			for effective_date in ("2026-11-05", "2026-11-01"):
				request = _request(effective_date)
				request["target_shift_group"] = "HC"
				with self.subTest(effective_date=effective_date), self.assertRaises(
					frappe.ValidationError
				):
					_preview(**request)

		preview_normal.assert_not_called()
		preview_backdated.assert_not_called()

	@patch(
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.today",
		return_value="2026-11-05",
	)
	def test_execute_validates_hc_holiday_list_before_routing(self, _today):
		request = _request("2026-11-05")
		request["target_shift_group"] = "HC"
		with patch.object(
			workflow,
			"get_required_hc_holiday_list",
			side_effect=frappe.ValidationError("HC Holiday List is required"),
			create=True,
		), patch.object(
			workflow, "execute_bulk_shift_group_transfer"
		) as execute_normal, patch.object(
			workflow, "execute_backdated_shift_group_transfer"
		) as execute_backdated, self.assertRaises(frappe.ValidationError):
			_execute(**request)

		execute_normal.assert_not_called()
		execute_backdated.assert_not_called()

	@patch(
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.today",
		return_value="2026-11-05",
	)
	@patch(
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.preview_backdated_shift_group_transfer"
	)
	def test_preview_routes_past_date_to_backdated_service(self, preview_backdated, _today):
		preview_backdated.return_value = {
			"mode": "BACKDATED",
			"counts": {"READY": 1},
			"rows": [{"employee": "EMP-001"}],
		}

		result = _preview(**_request())

		self.assertEqual(result["mode"], "BACKDATED")
		self.assertEqual(result["employees"], 1)
		self.assertEqual(result["target_shift_group"], "3")
		self.assertEqual(result["effective_date"], "2026-11-01")
		preview_backdated.assert_called_once_with(**_request())

	@patch(
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.today",
		return_value="2026-11-05",
	)
	@patch(
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.preview_bulk_shift_group_transfer"
	)
	def test_preview_routes_today_and_future_to_normal_service(self, preview_normal, _today):
		preview_normal.return_value = {
			"counts": {"READY": 1},
			"rows": [{"employee": "EMP-001"}],
			"employees": 1,
		}
		for effective_date in ("2026-11-05", "2026-11-06"):
			with self.subTest(effective_date=effective_date):
				result = _preview(**_request(effective_date))
				self.assertEqual(result["mode"], "NORMAL")
				self.assertEqual(result["effective_date"], effective_date)

		self.assertEqual(preview_normal.call_count, 2)

	@patch(
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.today",
		return_value="2026-11-05",
	)
	@patch(
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.execute_backdated_shift_group_transfer"
	)
	def test_execute_does_not_trust_client_mode(self, execute_backdated, _today):
		execute_backdated.return_value = {"status": "COMPLETED", "employees": 1}

		result = _execute(
			**_request(),
			preview_token="token-1",
			confirmation_text="XÁC NHẬN HỒI TỐ",
		)

		self.assertEqual(result["mode"], "BACKDATED")
		execute_backdated.assert_called_once()
		with self.assertRaises(TypeError):
			_execute(**_request(), mode="NORMAL")

	@patch(
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.today",
		return_value="2026-11-05",
	)
	@patch(
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.execute_backdated_shift_group_transfer"
	)
	def test_backdated_execute_forwards_token_and_phrase(self, execute_backdated, _today):
		execute_backdated.return_value = {"status": "COMPLETED", "employees": 1}
		request = _request()

		_execute(
			**request,
			preview_token="token-1",
			confirmation_text="XÁC NHẬN HỒI TỐ",
		)

		execute_backdated.assert_called_once_with(
			**request,
			preview_token="token-1",
			confirmation_text="XÁC NHẬN HỒI TỐ",
		)

	@patch(
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.today",
		return_value="2026-11-05",
	)
	@patch(
		"vinatex.vnt_hr.shift_management.shift_group_transfer_workflow.execute_bulk_shift_group_transfer"
	)
	def test_facade_normalizes_common_result_keys(self, execute_normal, _today):
		execute_normal.return_value = {
			"status": "QUEUED",
			"job_id": "job-1",
			"employees": 1,
		}

		result = _execute(**_request("2026-11-06"))

		self.assertEqual(
			result,
			{
				"status": "QUEUED",
				"job_id": "job-1",
				"employees": 1,
				"mode": "NORMAL",
				"target_shift_group": "3",
				"effective_date": "2026-11-06",
			},
		)
		execute_normal.assert_called_once_with(**_request("2026-11-06"))
