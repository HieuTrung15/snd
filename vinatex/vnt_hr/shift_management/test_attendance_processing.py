from datetime import date, datetime, time
from unittest import TestCase
from unittest.mock import patch

import frappe

from vinatex.vnt_hr.attendance_processing import (
	_nominal_shift_datetimes,
	_repair_existing_attendance,
	_select_checkin_window,
	calculate_attendance_details,
	get_log_presence,
)


def _window(
	start,
	end,
	*,
	work_date=date(2026, 10, 6),
	late=0,
	early=0,
	enable_marking=1,
	mode="Alternating entries as IN and OUT during the same shift",
):
	shift_doc = frappe._dict(
		start_time=start,
		end_time=end,
		enable_auto_attendance=0,
		determine_check_in_and_check_out=mode,
		working_hours_calculation_based_on="First Check-in and Last Check-out",
		enable_late_entry_marking=enable_marking,
		late_entry_grace_period=late,
		enable_early_exit_marking=enable_marking,
		early_exit_grace_period=early,
		working_hours_threshold_for_absent=0,
		working_hours_threshold_for_half_day=0,
	)
	start_datetime, end_datetime = _nominal_shift_datetimes(work_date, shift_doc)
	return frappe._dict(
		employee="EMP-001",
		work_date=work_date,
		shift_type="Test Shift",
		shift_doc=shift_doc,
		start_datetime=start_datetime,
		end_datetime=end_datetime,
		is_overnight=end_datetime.date() > start_datetime.date(),
	)


def _log(value, log_type=""):
	return frappe._dict(time=value, log_type=log_type)


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

	def test_one_punch_is_not_present(self):
		window = _window(time(6), time(14))
		details = calculate_attendance_details(
			window, [_log(datetime(2026, 10, 6, 5, 55))]
		)
		self.assertEqual(details.status, "Absent")
		self.assertEqual(details.working_hours, 0)

	def test_strict_early_in_and_late_out_belong_to_current_work_date(self):
		strict_mode = "Strictly based on Log Type in Employee Checkin"
		windows = [
			_window(
				time(7, 30),
				time(17),
				work_date=date(2026, 10, day),
				mode=strict_mode,
			)
			for day in (5, 6, 7)
		]
		self.assertEqual(
			_select_checkin_window(
				_log(datetime(2026, 10, 6, 5, 30), "IN"), windows
			).work_date,
			date(2026, 10, 6),
		)
		self.assertEqual(
			_select_checkin_window(
				_log(datetime(2026, 10, 6, 20), "OUT"), windows
			).work_date,
			date(2026, 10, 6),
		)

	def test_day_shift_uses_calendar_work_date_without_minute_buffer(self):
		windows = [
			_window(time(6), time(14), work_date=date(2026, 10, day))
			for day in (5, 6, 7)
		]
		self.assertEqual(
			_select_checkin_window(
				_log(datetime(2026, 10, 6, 21, 59), "OUT"), windows
			).work_date,
			date(2026, 10, 6),
		)
		self.assertEqual(
			_select_checkin_window(
				_log(datetime(2026, 10, 6, 23, 59), "OUT"), windows
			).work_date,
			date(2026, 10, 6),
		)
		self.assertEqual(
			_select_checkin_window(
				_log(datetime(2026, 10, 7, 0, 1), "IN"), windows
			).work_date,
			date(2026, 10, 7),
		)

	def test_overnight_late_punch_stays_with_start_work_date(self):
		windows = [
			_window(time(22), time(6), work_date=date(2026, 10, day))
			for day in (6, 7)
		]
		self.assertEqual(
			_select_checkin_window(
				_log(datetime(2026, 10, 7, 7), "IN"), windows
			).work_date,
			date(2026, 10, 6),
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

	@patch("vinatex.vnt_hr.attendance_processing.update_attendance_in_checkins")
	@patch("vinatex.vnt_hr.attendance_processing.frappe.db.set_value")
	def test_existing_absent_is_repaired_to_present(self, set_value, link_checkins):
		window = _window(time(6), time(14))
		logs = [
			frappe._dict(
				name="LOG-IN",
				time=datetime(2026, 10, 6, 5, 55),
				log_type="",
				attendance=None,
			),
			frappe._dict(
				name="LOG-OUT",
				time=datetime(2026, 10, 6, 14, 5),
				log_type="",
				attendance=None,
			),
		]
		attendance = frappe._dict(
			name="ATT-001",
			status="Absent",
			leave_type=None,
			shift="Test Shift",
			in_time=None,
			out_time=None,
			working_hours=0,
			late_entry=0,
			early_exit=0,
		)

		self.assertEqual(
			_repair_existing_attendance(attendance, window, logs),
			1,
		)
		updates = set_value.call_args.args[2]
		self.assertEqual(updates["status"], "Present")
		self.assertEqual(updates["in_time"], datetime(2026, 10, 6, 5, 55))
		self.assertEqual(updates["out_time"], datetime(2026, 10, 6, 14, 5))
		link_checkins.assert_called_once_with(["LOG-IN", "LOG-OUT"], "ATT-001")

	@patch("vinatex.vnt_hr.attendance_processing.update_attendance_in_checkins")
	@patch("vinatex.vnt_hr.attendance_processing.frappe.db.set_value")
	def test_existing_present_with_one_punch_is_repaired_to_absent(
		self, set_value, _link_checkins
	):
		window = _window(time(6), time(14))
		logs = [
			frappe._dict(
				name="LOG-IN",
				time=datetime(2026, 10, 6, 5, 55),
				log_type="",
				attendance=None,
			)
		]
		attendance = frappe._dict(
			name="ATT-001",
			status="Present",
			leave_type=None,
			shift="Test Shift",
			in_time=None,
			out_time=None,
			working_hours=0,
			late_entry=0,
			early_exit=0,
		)

		self.assertEqual(
			_repair_existing_attendance(attendance, window, logs),
			1,
		)
		self.assertEqual(set_value.call_args.args[2]["status"], "Absent")

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
