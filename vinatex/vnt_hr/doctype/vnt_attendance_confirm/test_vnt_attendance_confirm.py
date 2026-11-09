from datetime import date, datetime, time
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vinatex.vnt_hr.attendance_processing import (
	_nominal_shift_datetimes,
	load_checkins_for_windows,
)
from vinatex.vnt_hr.doctype.vnt_attendance_confirm import (
	vnt_attendance_confirm as attendance_confirm_module,
)
from vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm import (
	_compute_status,
	_detect_confirmation_issue,
	_resolve_date_range,
	_upsert_employee_confirmation,
	make_attendance_confirm,
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


def _admin_window(shift_type="Hành chính"):
	shift_doc = frappe._dict(
		start_time=time(7, 30),
		end_time=time(16, 30),
		determine_check_in_and_check_out=(
			"Strictly based on Log Type in Employee Checkin"
		),
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
		shift_group=None,
		shift_type=shift_type,
		start_datetime=start_datetime,
		end_datetime=end_datetime,
	)


def _owned_window(work_date, start_time, end_time, shift_type):
	shift_doc = frappe._dict(
		start_time=start_time,
		end_time=end_time,
		determine_check_in_and_check_out=(
			"Strictly based on Log Type in Employee Checkin"
		),
		working_hours_calculation_based_on="First Check-in and Last Check-out",
		enable_late_entry_marking=0,
		late_entry_grace_period=0,
		enable_early_exit_marking=0,
		early_exit_grace_period=0,
		working_hours_threshold_for_absent=0,
		working_hours_threshold_for_half_day=0,
	)
	start_datetime, end_datetime = _nominal_shift_datetimes(work_date, shift_doc)
	return frappe._dict(
		employee="NMSVNĐ00175",
		work_date=work_date,
		shift_doc=shift_doc,
		shift_group=None,
		shift_type=shift_type,
		start_datetime=start_datetime,
		end_datetime=end_datetime,
		actual_start=start_datetime,
		actual_end=end_datetime,
		is_overnight=end_datetime.date() > start_datetime.date(),
		is_off=False,
	)


def _log(hour, minute=0, log_type="", second=0):
	return frappe._dict(
		time=datetime(2026, 10, 7, hour, minute, second),
		log_type=log_type,
	)


class _FakeRow(frappe._dict):
	def set(self, key, value):
		self[key] = value


class _FakeConfirmation:
	def __init__(self, items=None):
		self.items = list(items or [])
		self.flags = frappe._dict()
		self.saved = False
		self.inserted = False

	def get(self, key):
		return getattr(self, key, None)

	def remove(self, row):
		self.items.remove(row)

	def append(self, key, value):
		assert key == "items"
		row = _FakeRow(value)
		self.items.append(row)
		return row

	def save(self, **kwargs):
		self.saved = True

	def insert(self, **kwargs):
		self.inserted = True


def _employee(department="Sản xuất"):
	return frappe._dict(
		name="NMSVNĐ00175",
		employee_name="Nguyễn Thị Oanh",
		company="Nhà máy Sợi Vinatex Nam Định",
		department=department,
	)


class TestVNTAttendanceConfirm(TestCase):
	@patch(
		"vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.today",
		return_value="2026-11-05",
	)
	def test_explicit_range_ending_today_is_capped_at_yesterday(self, _today):
		self.assertEqual(
			_resolve_date_range("2026-11-01", "2026-11-05"),
			(date(2026, 11, 1), date(2026, 11, 4)),
		)

	@patch(
		"vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.today",
		return_value="2026-11-05",
	)
	def test_range_containing_only_today_is_rejected(self, _today):
		with (
			patch(
				"vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm._",
				side_effect=lambda message: message,
			),
			patch.object(frappe, "throw", side_effect=frappe.ValidationError),
			self.assertRaises(frappe.ValidationError),
		):
			_resolve_date_range("2026-11-05", "2026-11-05")

	def test_presence_only_policy_applies_to_exact_departments_on_admin_shift(self):
		for department in (
			"Vào bông - NMSVNĐ",
			"Công đoạn Đóng gói - NMSVNĐ",
		):
			with self.subTest(department=department):
				self.assertTrue(
					attendance_confirm_module._uses_presence_only_admin_policy(
						_employee(department), _admin_window()
					)
				)

	def test_presence_only_policy_uses_current_employee_department(self):
		employee = _employee("Vào bông - NMSVNĐ")
		self.assertTrue(
			attendance_confirm_module._uses_presence_only_admin_policy(
				employee, _admin_window()
			)
		)

		employee.department = "Sản xuất"
		self.assertFalse(
			attendance_confirm_module._uses_presence_only_admin_policy(
				employee, _admin_window()
			)
		)

	def test_presence_only_policy_requires_admin_shift(self):
		self.assertFalse(
			attendance_confirm_module._uses_presence_only_admin_policy(
				_employee("Vào bông - NMSVNĐ"), _admin_window("Sáng")
			)
		)

	def test_presence_only_completed_rapid_in_out_pair_needs_no_explanation(self):
		issue = _detect_confirmation_issue(
			employee=_employee("Vào bông - NMSVNĐ"),
			window=_admin_window(),
			planned_logs=[_log(6, 2, "IN", 34), _log(6, 2, "OUT", 36)],
			outside_logs=[],
			day_type="work",
		)
		self.assertIsNone(issue)

	@patch(
		"vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.today",
		return_value="2026-11-05",
	)
	def test_confirmation_skips_overnight_window_that_ends_on_current_date(
		self, _today
	):
		employee = _employee("Sản xuất")
		work_date = date(2026, 11, 4)
		window = _owned_window(work_date, time(22), time(6), "Đêm")
		key = (employee.name, work_date)
		with (
			patch.object(attendance_confirm_module, "_assert_hr_access"),
			patch.object(
				attendance_confirm_module,
				"get_active_employees",
				return_value=[employee],
			),
			patch.object(
				attendance_confirm_module,
				"build_shift_windows",
				return_value={key: window},
			),
			patch.object(
				attendance_confirm_module,
				"load_checkins_for_windows",
				return_value=(
					{key: [frappe._dict(time=datetime(2026, 11, 4, 22), log_type="IN")]},
					{},
					{},
				),
			),
			patch.object(attendance_confirm_module, "load_holiday_context"),
			patch.object(
				attendance_confirm_module,
				"_load_excused_days",
				return_value=set(),
			),
			patch.object(
				attendance_confirm_module,
				"classify_work_date",
				return_value="work",
			),
			patch.object(
				attendance_confirm_module,
				"_detect_confirmation_issue",
				return_value=None,
			) as detect_issue,
		):
			result = make_attendance_confirm.__wrapped__(
				from_date="2026-11-04",
				to_date="2026-11-05",
				dry_run=True,
			)

		self.assertEqual(result["Đến ngày"], work_date)
		detect_issue.assert_not_called()

	@patch(
		"vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.today",
		return_value="2026-11-05",
	)
	def test_confirmation_keeps_off_window_without_end_datetime(self, _today):
		employee = _employee("Vào bông - NMSVNĐ")
		work_date = date(2026, 11, 4)
		window = frappe._dict(
			employee=employee.name,
			work_date=work_date,
			shift_type=None,
			shift_group=None,
			start_datetime=None,
			end_datetime=None,
			is_off=True,
		)
		key = (employee.name, work_date)
		outside_log = frappe._dict(
			time=datetime(2026, 11, 4, 8), log_type="IN"
		)
		with (
			patch.object(attendance_confirm_module, "_assert_hr_access"),
			patch.object(
				attendance_confirm_module,
				"get_active_employees",
				return_value=[employee],
			),
			patch.object(
				attendance_confirm_module,
				"build_shift_windows",
				return_value={key: window},
			),
			patch.object(
				attendance_confirm_module,
				"load_checkins_for_windows",
				return_value=({}, {key: [outside_log]}, {key: [outside_log]}),
			),
			patch.object(attendance_confirm_module, "load_holiday_context"),
			patch.object(
				attendance_confirm_module,
				"_load_excused_days",
				return_value=set(),
			),
			patch.object(
				attendance_confirm_module,
				"classify_work_date",
				return_value="off",
			),
			patch.object(
				attendance_confirm_module,
				"_detect_confirmation_issue",
				return_value=None,
			) as detect_issue,
		):
			make_attendance_confirm.__wrapped__(
				from_date="2026-11-04",
				to_date="2026-11-05",
				dry_run=True,
			)

		detect_issue.assert_called_once()

	def test_presence_only_pair_outside_admin_hours_needs_no_explanation(self):
		issue = _detect_confirmation_issue(
			employee=_employee("Công đoạn Đóng gói - NMSVNĐ"),
			window=_admin_window(),
			planned_logs=[],
			outside_logs=[_log(5, 56, "IN"), _log(18, 5, "OUT")],
			day_type="work",
		)
		self.assertIsNone(issue)

	@patch("vinatex.vnt_hr.attendance_processing.frappe.get_all")
	def test_presence_only_uses_calendar_logs_owned_by_previous_overnight_shift(
		self, get_all
	):
		employee = _employee("Vào bông - NMSVNĐ")
		windows = {
			(employee.name, work_date): _owned_window(
				work_date,
				time(22) if work_date == date(2026, 10, 6) else time(7, 30),
				time(6) if work_date == date(2026, 10, 6) else time(16, 30),
				"Đêm" if work_date == date(2026, 10, 6) else "Hành chính",
			)
			for work_date in (
				date(2026, 10, 5),
				date(2026, 10, 6),
				date(2026, 10, 7),
				date(2026, 10, 8),
			)
		}
		get_all.return_value = [
			frappe._dict(
				name="CHECKIN-IN",
				employee=employee.name,
				time=datetime(2026, 10, 7, 5, 56),
				log_type="IN",
				attendance=None,
			),
			frappe._dict(
				name="CHECKIN-OUT",
				employee=employee.name,
				time=datetime(2026, 10, 7, 9, 18),
				log_type="OUT",
				attendance=None,
			),
		]

		planned, outside, calendar_logs = load_checkins_for_windows(
			[employee],
			windows,
			date(2026, 10, 6),
			date(2026, 10, 7),
			include_calendar_logs=True,
			checkin_end_exclusive=datetime(2026, 10, 8),
		)
		key = (employee.name, date(2026, 10, 7))
		self.assertEqual([row.log_type for row in planned[key]], ["OUT"])
		self.assertEqual(
			[row.log_type for row in calendar_logs[key]], ["IN", "OUT"]
		)
		issue = _detect_confirmation_issue(
			employee=employee,
			window=windows[key],
			planned_logs=planned[key],
			outside_logs=outside[key],
			calendar_logs=calendar_logs[key],
			day_type="work",
		)
		self.assertIsNone(issue)
		checkin_filters = get_all.call_args.kwargs["filters"]
		self.assertEqual(
			checkin_filters["time"][1][1],
			datetime(2026, 10, 7, 23, 59, 59, 999999),
		)

	def test_presence_only_without_logs_requires_no_checkin_explanation(self):
		issue = _detect_confirmation_issue(
			employee=_employee("Vào bông - NMSVNĐ"),
			window=_admin_window(),
			planned_logs=[],
			outside_logs=[],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "WORKDAY_NO_CHECKIN")

	def test_presence_only_in_without_out_requires_missing_out_explanation(self):
		issue = _detect_confirmation_issue(
			employee=_employee("Vào bông - NMSVNĐ"),
			window=_admin_window(),
			planned_logs=[_log(5, 56, "IN")],
			outside_logs=[],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "MISSING_OUT")

	def test_presence_only_out_without_in_requires_missing_in_explanation(self):
		issue = _detect_confirmation_issue(
			employee=_employee("Công đoạn Đóng gói - NMSVNĐ"),
			window=_admin_window(),
			planned_logs=[],
			outside_logs=[_log(9, 18, "OUT")],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "MISSING_IN")

	def test_presence_only_duplicate_in_and_malformed_logs_still_miss_out(self):
		issue = _detect_confirmation_issue(
			employee=_employee("Vào bông - NMSVNĐ"),
			window=_admin_window(),
			planned_logs=[_log(5, 56, "IN"), _log(5, 57, "in")],
			outside_logs=[_log(9, 18), _log(9, 19, "BREAK")],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "MISSING_OUT")

	def test_presence_only_malformed_logs_have_no_valid_presence(self):
		issue = _detect_confirmation_issue(
			employee=_employee("Vào bông - NMSVNĐ"),
			window=_admin_window(),
			planned_logs=[_log(6, 0), _log(9, 0, "BREAK")],
			outside_logs=[],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "WORKDAY_NO_CHECKIN")

	def test_presence_only_off_day_keeps_off_confirmation(self):
		issue = _detect_confirmation_issue(
			employee=_employee("Vào bông - NMSVNĐ"),
			window=_admin_window(),
			planned_logs=[_log(6, 0, "IN"), _log(9, 0, "OUT")],
			outside_logs=[],
			day_type="off",
		)
		self.assertEqual(issue.issue_code, "OFF_WITH_CHECKIN")

	def test_standard_department_still_reports_admin_early_exit(self):
		issue = _detect_confirmation_issue(
			employee=_employee("Sản xuất"),
			window=_admin_window(),
			planned_logs=[_log(7, 30, "IN"), _log(14, 0, "OUT")],
			outside_logs=[],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "EARLY_EXIT")

	def test_upsert_deletes_parent_after_last_unresolved_row_disappears(self):
		doc = _FakeConfirmation([
			_FakeRow(date=date(2026, 11, 1), confirm=None),
		])

		with (
			patch.object(
				frappe,
				"db",
				SimpleNamespace(get_value=lambda *args, **kwargs: "GTCC-EMPTY"),
			),
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			result = _upsert_employee_confirmation(
				_employee(), date(2026, 11, 1), date(2026, 11, 4), []
			)

		self.assertEqual(result, (0, 0, 1))
		self.assertEqual(doc.items, [])
		self.assertFalse(doc.saved)
		delete_doc.assert_called_once_with(
			"VNT Attendance Confirm", "GTCC-EMPTY", ignore_permissions=True
		)

	def test_upsert_keeps_parent_with_confirmed_history(self):
		confirmed_row = _FakeRow(
			date=date(2026, 11, 1),
			confirm="Đồng ý",
			type="Có xác nhận của quản đốc",
		)
		doc = _FakeConfirmation([confirmed_row])

		with (
			patch.object(
				frappe,
				"db",
				SimpleNamespace(get_value=lambda *args, **kwargs: "GTCC-HISTORY"),
			),
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			result = _upsert_employee_confirmation(
				_employee(), date(2026, 11, 1), date(2026, 11, 4), []
			)

		self.assertEqual(result, (0, 0, 0))
		self.assertEqual(doc.items, [confirmed_row])
		self.assertFalse(doc.saved)
		delete_doc.assert_not_called()

	def test_upsert_locks_and_reloads_before_deciding_to_delete(self):
		stale_doc = _FakeConfirmation([
			_FakeRow(date=date(2026, 11, 1), confirm=None),
		])
		confirmed_doc = _FakeConfirmation([
			_FakeRow(
				date=date(2026, 11, 1),
				confirm="Đồng ý",
				type="HR vừa xác nhận",
			),
		])

		def load_doc(_doctype, _name, for_update=False):
			return confirmed_doc if for_update else stale_doc

		with (
			patch.object(
				frappe,
				"db",
				SimpleNamespace(get_value=lambda *args, **kwargs: "GTCC-CONCURRENT"),
			),
			patch.object(frappe, "get_doc", side_effect=load_doc) as get_doc,
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			result = _upsert_employee_confirmation(
				_employee(), date(2026, 11, 1), date(2026, 11, 4), []
			)

		self.assertEqual(result, (0, 0, 0))
		get_doc.assert_called_once_with(
			"VNT Attendance Confirm", "GTCC-CONCURRENT", for_update=True
		)
		delete_doc.assert_not_called()

	def test_upsert_adds_current_issue_to_existing_empty_parent(self):
		doc = _FakeConfirmation()
		issue = frappe._dict(
			date=date(2026, 11, 4),
			issue_code="MISSING_OUT",
			issue_type="Chỉ có giờ vào hợp lệ trong ca",
		)

		with (
			patch.object(
				frappe,
				"db",
				SimpleNamespace(get_value=lambda *args, **kwargs: "GTCC-REFILLED"),
			),
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "delete_doc") as delete_doc,
		):
			result = _upsert_employee_confirmation(
				_employee(), date(2026, 11, 1), date(2026, 11, 4), [issue]
			)

		self.assertEqual(result, (0, 1, 0))
		self.assertTrue(doc.saved)
		self.assertEqual(len(doc.items), 1)
		self.assertEqual(doc.items[0].issue_code, "MISSING_OUT")
		delete_doc.assert_not_called()

	def test_upsert_without_parent_or_issues_returns_three_zeroes(self):
		with patch.object(
			frappe,
			"db",
			SimpleNamespace(get_value=lambda *args, **kwargs: None),
		):
			result = _upsert_employee_confirmation(
				_employee(), date(2026, 11, 1), date(2026, 11, 4), []
			)

		self.assertEqual(result, (0, 0, 0))

	def test_make_attendance_confirm_exposes_deleted_counter(self):
		with (
			patch(
				"vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.today",
				return_value="2026-11-05",
			),
			patch(
				"vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm._assert_hr_access"
			),
			patch(
				"vinatex.vnt_hr.doctype.vnt_attendance_confirm.vnt_attendance_confirm.get_active_employees",
				return_value=[],
			),
		):
			result = make_attendance_confirm.__wrapped__(
				from_date="2026-11-01", to_date="2026-11-04"
			)

		self.assertEqual(result["Số phiếu đã xóa"], 0)

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

	def test_workday_without_any_punch_requires_confirmation(self):
		issue = _detect_confirmation_issue(
			window=_window(),
			planned_logs=[],
			outside_logs=[],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "WORKDAY_NO_CHECKIN")
		self.assertEqual(issue.outside_checkin_count, 0)
		self.assertEqual(issue.planned_checkin_count, 0)

	def test_one_valid_start_punch_is_missing_out(self):
		issue = _detect_confirmation_issue(
			window=_window(),
			planned_logs=[_log(5, 58)],
			outside_logs=[],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "MISSING_OUT")

	def test_untyped_checkins_that_cannot_form_in_out_require_confirmation(self):
		window = _window()
		window.shift_doc.determine_check_in_and_check_out = (
			"Strictly based on Log Type in Employee Checkin"
		)
		issue = _detect_confirmation_issue(
			window=window,
			planned_logs=[_log(8), _log(13)],
			outside_logs=[],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "WORKDAY_INVALID_CHECKINS")
		self.assertEqual(issue.planned_checkin_count, 2)

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

	def test_complete_pair_with_outside_punches_requires_overtime_confirmation(self):
		issue = _detect_confirmation_issue(
			window=_window(),
			planned_logs=[_log(5, 58), _log(14, 2)],
			outside_logs=[_log(17), _log(19)],
			day_type="work",
		)
		self.assertEqual(issue.issue_code, "WORKDAY_OVERTIME")
		self.assertEqual(issue.evidence_code, "+")
		self.assertEqual(issue.outside_checkin_count, 2)

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
