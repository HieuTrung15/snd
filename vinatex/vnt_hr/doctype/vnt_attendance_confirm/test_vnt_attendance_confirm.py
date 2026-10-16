from datetime import date, datetime, time
from unittest import TestCase

import frappe

from vinatex.vnt_hr.attendance_processing import _nominal_shift_datetimes
from vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm import (
	_compute_status,
	_detect_confirmation_issue,
)


def _window():
	shift_doc = frappe._dict(
		start_time=time(6),
		end_time=time(14),
		determine_check_in_and_check_out="Alternating entries as IN and OUT during the same shift",
		working_hours_calculation_based_on="First Check-in and Last Check-out",
		enable_late_entry_marking=0,
		late_entry_grace_period=0,
		enable_early_exit_marking=0,
		early_exit_grace_period=0,
		working_hours_threshold_for_absent=0,
		working_hours_threshold_for_half_day=0,
	)
	start_datetime, end_datetime = _nominal_shift_datetimes(
		date(2026, 10, 7), shift_doc
	)
	return frappe._dict(
		shift_doc=shift_doc,
		shift_group="Kíp 1",
		shift_type="Sáng",
		start_datetime=start_datetime,
		end_datetime=end_datetime,
	)


def _log(hour, minute=0, log_type=""):
	return frappe._dict(
		time=datetime(2026, 10, 7, hour, minute),
		log_type=log_type,
	)


class TestVNTAttendanceConfirm(TestCase):
	def test_off_single_outside_punch_requires_confirmation(self):
		issue = _detect_confirmation_issue(
			window=frappe._dict(shift_group="Kíp 1", shift_type=None),
			planned_logs=[],
			outside_logs=[_log(21, 32)],
			day_type="off",
		)
		self.assertEqual(issue.issue_code, "OFF_WITH_CHECKIN")
		self.assertEqual(issue.evidence_code, "+1")
		self.assertEqual(issue.outside_checkin_count, 1)

	def test_off_multiple_outside_punches_use_plus_evidence(self):
		issue = _detect_confirmation_issue(
			window=frappe._dict(shift_group="Kíp 1", shift_type=None),
			planned_logs=[],
			outside_logs=[_log(8), _log(17)],
			day_type="off",
		)
		self.assertEqual(issue.evidence_code, "+")
		self.assertEqual(issue.outside_checkin_count, 2)

	def test_off_treats_punch_in_nominal_window_as_outside_work_plan(self):
		issue = _detect_confirmation_issue(
			window=_window(),
			planned_logs=[_log(8)],
			outside_logs=[],
			day_type="off",
		)
		self.assertEqual(issue.issue_code, "OFF_WITH_CHECKIN")
		self.assertEqual(issue.evidence_code, "+1")
		self.assertEqual(issue.planned_checkin_count, 0)
		self.assertEqual(issue.outside_checkin_count, 1)

	def test_workday_with_only_outside_punches_is_flagged(self):
		issue = _detect_confirmation_issue(
			window=_window(),
			planned_logs=[],
			outside_logs=[_log(20), _log(21)],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "WORKDAY_OUTSIDE_ONLY")

	def test_one_valid_start_punch_is_missing_out(self):
		issue = _detect_confirmation_issue(
			window=_window(),
			planned_logs=[_log(5, 58)],
			outside_logs=[],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "MISSING_OUT")

	def test_one_valid_end_punch_is_missing_in(self):
		issue = _detect_confirmation_issue(
			window=_window(),
			planned_logs=[_log(14, 2)],
			outside_logs=[],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "MISSING_IN")

	def test_complete_valid_pair_does_not_require_confirmation(self):
		issue = _detect_confirmation_issue(
			window=_window(),
			planned_logs=[_log(5, 58), _log(14, 2)],
			outside_logs=[],
			day_type="work",
		)
		self.assertIsNone(issue)

	def test_complete_pair_with_early_exit_requires_confirmation(self):
		issue = _detect_confirmation_issue(
			window=_window(),
			planned_logs=[_log(5, 58), _log(13, 30)],
			outside_logs=[],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "EARLY_EXIT")
		self.assertEqual(issue.issue_type, "Về sớm so với ca kế hoạch")
		self.assertEqual(issue.time_out, datetime(2026, 10, 7, 13, 30))

	def test_early_exit_within_shift_grace_does_not_require_confirmation(self):
		window = _window()
		window.shift_doc.early_exit_grace_period = 30
		issue = _detect_confirmation_issue(
			window=window,
			planned_logs=[_log(5, 58), _log(13, 45)],
			outside_logs=[],
			day_type="work",
		)
		self.assertIsNone(issue)

	def test_status_is_complete_after_one_level_decision(self):
		doc = frappe._dict(
			items=[frappe._dict(type="Có xác nhận của quản đốc", confirm="Đồng ý")]
		)
		self.assertEqual(_compute_status(doc), "Đã xác nhận")
