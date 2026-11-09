"""Same-day (effective date = today) transfer when today already has punches."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from vinatex.vnt_hr.shift_management import shift_group_transfer_service as service

TODAY = "2026-11-09"


def _throw(message, *args, **kwargs):
	raise frappe.ValidationError(message)


def _request():
	return {
		"employees": ["EMP-001"],
		"target_shift_group": "HC",
		"target_company": "Test Company",
		"effective_date": frappe.utils.getdate(TODAY),
		"membership_end_date": frappe.utils.getdate("2026-12-31"),
		"generate_until": frappe.utils.getdate("2026-12-31"),
		"note": "Same-day transfer",
	}


def _employee():
	return frappe._dict(
		name="EMP-001",
		employee_name="Employee One",
		company="Test Company",
		custom_shift_group="1",
		default_shift=None,
	)


def _membership():
	return frappe._dict(
		name="MEM-1",
		shift_group="1",
		from_date="2026-01-01",
		to_date="2026-12-31",
	)


def _auto_assignment(name, work_date, *, end_date=None):
	return frappe._dict(
		name=name,
		employee="EMP-001",
		start_date=work_date,
		end_date=end_date or work_date,
		shift_type="Chiều",
		custom_shift_group="1",
		custom_generated_by_shift_group=1,
		custom_assignment_source="Kíp tự động",
	)


def _preview(assignments, attendance_dates=(), checkin_dates=()):
	with patch.object(service, "today", return_value=TODAY):
		return service._preview_employee(
			_employee(),
			_request(),
			[_membership()],
			assignments,
			{frappe.utils.getdate(value) for value in attendance_dates},
			{frappe.utils.getdate(value) for value in checkin_dates},
			{"1", "HC"},
		)


class TestSameDayTransferPreview(TestCase):
	def test_today_checkin_does_not_block_and_replaces_today_assignment(self):
		row = _preview(
			[
				_auto_assignment("ASG-TODAY", TODAY),
				_auto_assignment("ASG-TOMORROW", "2026-11-10"),
			],
			checkin_dates=[TODAY],
		)

		self.assertEqual(row["status"], "READY")
		self.assertEqual(row["blockers"], [])
		self.assertEqual(row["assignment_names_to_replace_today"], ["ASG-TODAY"])
		self.assertEqual(row["assignment_names_to_cancel"], ["ASG-TOMORROW"])
		self.assertTrue(row["has_current_day_checkins"])

	def test_today_attendance_still_blocks(self):
		row = _preview(
			[_auto_assignment("ASG-TODAY", TODAY)],
			attendance_dates=[TODAY],
			checkin_dates=[TODAY],
		)

		self.assertEqual(row["status"], "BLOCKED")

	def test_checkin_on_a_later_date_still_blocks(self):
		row = _preview(
			[_auto_assignment("ASG-TOMORROW", "2026-11-10")],
			checkin_dates=["2026-11-10"],
		)

		self.assertEqual(row["status"], "BLOCKED")

	def test_multi_day_auto_assignment_with_today_checkin_blocks(self):
		row = _preview(
			[_auto_assignment("ASG-RANGE", TODAY, end_date="2026-11-12")],
			checkin_dates=[TODAY],
		)

		self.assertEqual(row["status"], "BLOCKED")
		self.assertEqual(row["assignment_names_to_replace_today"], [])

	def test_without_today_checkin_today_assignment_keeps_normal_cancel(self):
		row = _preview([_auto_assignment("ASG-TODAY", TODAY)])

		self.assertEqual(row["status"], "READY")
		self.assertEqual(row["assignment_names_to_cancel"], ["ASG-TODAY"])
		self.assertEqual(row["assignment_names_to_replace_today"], [])
		self.assertFalse(row["has_current_day_checkins"])


class TestSameDayTransferExecution(TestCase):
	def _run(self, preview):
		events = []
		assignment = SimpleNamespace(
			name="ASG-TODAY",
			employee="EMP-001",
			start_date=TODAY,
			end_date=TODAY,
			shift_type="Chiều",
			status="Active",
			docstatus=1,
			custom_generated_by_shift_group=1,
			custom_assignment_source="Kíp tự động",
			custom_shift_group="1",
			custom_schedule_date=TODAY,
			cancel=MagicMock(side_effect=AssertionError("HRMS cancel must not run")),
		)
		assignment.get = lambda fieldname, default=None: getattr(assignment, fieldname, default)
		comments = []
		set_value = MagicMock(side_effect=lambda *args, **kwargs: events.append("cancel_db"))

		def get_doc(doctype_or_values, name=None):
			if isinstance(doctype_or_values, dict):
				doc = MagicMock()
				doc.insert.side_effect = lambda **kwargs: comments.append(doctype_or_values)
				return doc
			return assignment

		fake_frappe = SimpleNamespace(
			get_doc=get_doc,
			db=SimpleNamespace(set_value=set_value),
			session=SimpleNamespace(user="hr@example.com"),
			throw=_throw,
		)

		def generate(*args, **kwargs):
			events.append("generate")
			return {"counts": {"CREATE": 1}}

		def resync(work_date, employee_names):
			events.append(("resync", work_date, list(employee_names)))
			return 1

		with patch.object(service, "_validate_request", return_value=_request()), patch.object(
			service, "_lock_employee_rows"
		), patch.object(service, "_build_preview", return_value=preview), patch.object(
			service, "_throw_if_blocked"
		), patch.object(service, "_apply_membership_change"), patch.object(
			service, "generate_shift_assignments", side_effect=generate
		), patch.object(service, "_assert_no_concurrent_usage"), patch.object(
			service,
			"sync_employee_current_shift_groups",
			return_value={"counts": {"UPDATED": 1}},
		), patch.object(
			service,
			"sync_checkin_shift_fields_for_date",
			side_effect=resync,
			create=True,
		), patch.object(service, "frappe", fake_frappe), patch.object(
			service, "today", return_value=TODAY
		), patch.object(
			service, "now_datetime", return_value="2026-11-09 09:00:00", create=True
		):
			result = service._run_bulk_shift_group_transfer(_request())
		return result, events, set_value, comments

	def test_today_assignment_is_cancelled_in_db_then_punches_resynced(self):
		preview = {
			"assignment_names_to_cancel": [],
			"assignment_names_to_replace_today": ["ASG-TODAY"],
			"rows": [
				{
					"employee": "EMP-001",
					"membership_action": "CLOSE_AND_CREATE",
					"has_current_day_checkins": True,
				}
			],
		}

		result, events, set_value, comments = self._run(preview)

		self.assertEqual(
			events,
			[
				"cancel_db",
				"generate",
				("resync", frappe.utils.getdate(TODAY), ["EMP-001"]),
			],
		)
		self.assertEqual(set_value.call_args.args[:2], ("Shift Assignment", "ASG-TODAY"))
		self.assertEqual(set_value.call_args.args[2]["docstatus"], 2)
		self.assertEqual(set_value.call_args.args[2]["status"], "Inactive")
		self.assertEqual(len(comments), 1)
		self.assertEqual(comments[0]["reference_name"], "ASG-TODAY")
		self.assertIn("Chiều", comments[0]["content"])
		self.assertEqual(result["current_day_assignments_replaced"], 1)
		self.assertEqual(result["current_day_checkins_resynced"], 1)

	def test_no_resync_when_nobody_has_today_checkins(self):
		preview = {
			"assignment_names_to_cancel": [],
			"assignment_names_to_replace_today": [],
			"rows": [
				{
					"employee": "EMP-001",
					"membership_action": "CLOSE_AND_CREATE",
					"has_current_day_checkins": False,
				}
			],
		}

		result, events, _set_value, _comments = self._run(preview)

		self.assertEqual(events, ["generate"])
		self.assertEqual(result["current_day_checkins_resynced"], 0)


class TestSameDayConcurrentUsageGuard(TestCase):
	def _assert(self, attendance_dates, checkin_dates):
		with patch.object(
			service,
			"_load_attendance_dates",
			return_value={"EMP-001": {frappe.utils.getdate(v) for v in attendance_dates}},
		), patch.object(
			service,
			"_load_checkin_dates",
			return_value={"EMP-001": {frappe.utils.getdate(v) for v in checkin_dates}},
		), patch.object(service, "today", return_value=TODAY), patch.object(
			service, "frappe", SimpleNamespace(throw=_throw)
		), patch.object(service, "_", side_effect=lambda message: message):
			service._assert_no_concurrent_usage(["EMP-001"], _request())

	def test_today_checkin_is_not_a_conflict(self):
		self._assert([], [TODAY])

	def test_today_attendance_is_still_a_conflict(self):
		with self.assertRaises(frappe.ValidationError):
			self._assert([TODAY], [TODAY])
