from datetime import date, datetime, time
from unittest import TestCase

import frappe

from vinatex.vnt_hr.attendance_processing import (
	_nominal_shift_datetimes,
	calculate_attendance_details,
	get_log_presence,
)


def _window(start, end, *, late=0, early=0, enable_marking=1):
	shift_doc = frappe._dict(
		start_time=start,
		end_time=end,
		enable_auto_attendance=0,
		determine_check_in_and_check_out="Alternating entries as IN and OUT during the same shift",
		working_hours_calculation_based_on="First Check-in and Last Check-out",
		enable_late_entry_marking=enable_marking,
		late_entry_grace_period=late,
		enable_early_exit_marking=enable_marking,
		early_exit_grace_period=early,
		working_hours_threshold_for_absent=0,
		working_hours_threshold_for_half_day=0,
	)
	start_datetime, end_datetime = _nominal_shift_datetimes(date(2026, 10, 6), shift_doc)
	return frappe._dict(
		shift_doc=shift_doc,
		start_datetime=start_datetime,
		end_datetime=end_datetime,
		is_overnight=end_datetime.date() > start_datetime.date(),
	)


def _log(value):
	return frappe._dict(time=value, log_type="")


class TestAttendanceProcessing(TestCase):
	def test_night_shift_keeps_start_date_as_work_date(self):
		window = _window(time(22), time(6))
		self.assertEqual(window.start_datetime, datetime(2026, 10, 6, 22))
		self.assertEqual(window.end_datetime, datetime(2026, 10, 7, 6))
		self.assertTrue(window.is_overnight)

	def test_alternating_one_punch_near_start_is_missing_out(self):
		window = _window(time(6), time(14))
		self.assertEqual(
			get_log_presence(window, [_log(datetime(2026, 10, 6, 5, 55))]),
			(True, False),
		)

	def test_alternating_one_punch_near_end_is_missing_in(self):
		window = _window(time(6), time(14))
		self.assertEqual(
			get_log_presence(window, [_log(datetime(2026, 10, 6, 14, 5))]),
			(False, True),
		)

	def test_overnight_pair_calculates_hours_and_flags(self):
		window = _window(time(22), time(6), late=5, early=5)
		details = calculate_attendance_details(
			window,
			[
				_log(datetime(2026, 10, 6, 22, 6)),
				_log(datetime(2026, 10, 7, 5, 54)),
			],
		)
		self.assertEqual(details.working_hours, 7.8)
		self.assertTrue(details.late_entry)
		self.assertTrue(details.early_exit)
		self.assertTrue(details.has_in)
		self.assertTrue(details.has_out)

	def test_attendance_mode_respects_disabled_marking_switches(self):
		window = _window(time(6), time(14), enable_marking=0)
		details = calculate_attendance_details(
			window,
			[
				_log(datetime(2026, 10, 6, 6, 1)),
				_log(datetime(2026, 10, 6, 13, 59)),
			],
		)
		self.assertFalse(details.late_entry)
		self.assertFalse(details.early_exit)

	def test_report_mode_detects_late_and_early_without_auto_attendance(self):
		window = _window(time(6), time(14), late=5, early=5, enable_marking=0)
		details = calculate_attendance_details(
			window,
			[
				_log(datetime(2026, 10, 6, 6, 6)),
				_log(datetime(2026, 10, 6, 13, 54)),
			],
			respect_marking_flags=False,
		)
		self.assertTrue(details.late_entry)
		self.assertTrue(details.early_exit)

	def test_report_mode_treats_grace_boundaries_as_on_time(self):
		window = _window(time(6), time(14), late=5, early=5, enable_marking=0)
		details = calculate_attendance_details(
			window,
			[
				_log(datetime(2026, 10, 6, 6, 5)),
				_log(datetime(2026, 10, 6, 13, 55)),
			],
			respect_marking_flags=False,
		)
		self.assertFalse(details.late_entry)
		self.assertFalse(details.early_exit)
