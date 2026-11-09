from datetime import date, datetime
from unittest import TestCase

import frappe

from vinatex.vnt_hr.report.báo_cáo_công_hàng_tháng.báo_cáo_công_hàng_tháng import (
	SUMMARY_COLUMNS,
	_make_workbook as make_attendance_workbook,
)
from vinatex.vnt_hr.report.báo_cáo_tăng_ca_hàng_tháng.báo_cáo_tăng_ca_hàng_tháng import (
	_make_workbook as make_overtime_workbook,
)
from vinatex.vnt_hr.report.monthly_report_common import (
	_apply_attendance_totals,
	_attendance_symbol,
	_build_day_record,
	_calculate_overtime_hours,
	_leave_symbol,
	_period_confirmation_documents,
	_shift_symbol,
)


class TestMonthlyReportCommon(TestCase):
	def test_leave_symbols_follow_hr_legend(self):
		self.assertEqual(_leave_symbol("Nghỉ ốm")[0], "Ô")
		self.assertEqual(_leave_symbol("Nghỉ mát")[0], "NM")
		self.assertEqual(_leave_symbol("Nghỉ cưới")[0], "CH")
		self.assertEqual(_leave_symbol("Nghỉ tang lễ")[0], "TL")
		self.assertEqual(_leave_symbol("Nghỉ bù")[0], "NB")
		self.assertEqual(_leave_symbol("Nghỉ không lương có lý do")[0], "R0")
		self.assertEqual(_leave_symbol("Nghỉ không lương không lý do")[0], "L0")

	def test_shift_symbols_match_handed_over_legend(self):
		self.assertEqual(_shift_symbol(frappe._dict(shift_type="Sáng", is_off=False)), "S")
		self.assertEqual(_shift_symbol(frappe._dict(shift_type="Chiều", is_off=False)), "C")
		self.assertEqual(
			_shift_symbol(frappe._dict(shift_type="Đêm", is_off=False, is_overnight=True)),
			"Đ",
		)
		self.assertEqual(_shift_symbol(frappe._dict(shift_type="Hành chính", is_off=False)), "X")

	def test_overtime_rounds_hours_after_planned_end_like_handed_over_sheet(self):
		employee = frappe._dict(default_shift="Hành chính", custom_shift_group="HC")
		window = frappe._dict(
			is_off=False,
			start_datetime=datetime(2026, 10, 1, 7, 30),
			end_datetime=datetime(2026, 10, 1, 17, 0),
		)
		planned = [
			frappe._dict(name="IN", time=datetime(2026, 10, 1, 7, 0)),
			frappe._dict(name="OUT", time=datetime(2026, 10, 1, 17, 0)),
		]
		outside = [frappe._dict(name="OT", time=datetime(2026, 10, 1, 19, 45))]
		self.assertEqual(
			_calculate_overtime_hours(
				employee=employee,
				day_type="work",
				window=window,
				planned_logs=planned,
				outside_logs=outside,
			),
			3.0,
		)

	def test_overtime_without_any_work_plan_is_not_invented(self):
		employee = frappe._dict(default_shift=None, custom_shift_group=None)
		logs = [
			frappe._dict(name="A", time=datetime(2026, 10, 1, 8, 0)),
			frappe._dict(name="B", time=datetime(2026, 10, 1, 17, 0)),
		]
		self.assertEqual(
			_calculate_overtime_hours(
				employee=employee,
				day_type="off",
				window=None,
				planned_logs=[],
				outside_logs=logs,
			),
			0.0,
		)

	def test_sunday_symbol_only_counts_actual_sunday_work(self):
		base = dict(
			employee=frappe._dict(),
			work_date=date(2026, 10, 4),
			day_type="off",
			window=None,
			shift_symbol="X",
			attendance=None,
			leave=None,
			holiday_context=frappe._dict(),
			working_hours=0,
		)
		self.assertEqual(_attendance_symbol(**base, technical_symbol="Off")[0], "")
		self.assertEqual(_attendance_symbol(**base, technical_symbol="+")[0], "CN")

	def test_short_work_hours_do_not_increase_full_workday_total(self):
		row = frappe._dict(tot_work_days=0.0, tot_work_hours=0.0)
		for fieldname in (
			"tot_night",
			"tot_sick",
			"tot_sunday",
			"tot_holiday",
			"tot_public_holiday",
			"tot_special_leave",
			"tot_paid_leave",
			"tot_family_leave",
			"tot_comp_leave",
			"tot_unpaid_reason",
			"tot_unpaid_no_reason",
		):
			row[fieldname] = 0.0
		_apply_attendance_totals(
			row,
			frappe._dict(category="short_work", units=1.0, working_hours=6.5),
		)
		self.assertEqual(row.tot_work_days, 0.0)
		self.assertEqual(row.tot_work_hours, 6.5)

	def test_short_work_symbol_ignores_custom_need_check(self):
		base = dict(
			work_date=date(2026, 10, 1),
			day_type="work",
			window=None,
			shift_symbol="X",
			technical_symbol="X",
			attendance=None,
			leave=None,
			holiday_context=frappe._dict(),
			working_hours=6.5,
		)
		for custom_need_check in (0, 1):
			self.assertEqual(
				_attendance_symbol(
					employee=frappe._dict(custom_need_check=custom_need_check),
					**base,
				),
				("6", "short_work", 1.0),
			)

	def _missing_out_day(self, can_open_confirmation):
		window = frappe._dict(
			is_off=False,
			shift_type="Hành chính",
			shift_group=None,
			shift_doc=frappe._dict(holiday_list=None),
			work_date=date(2026, 10, 1),
			start_datetime=datetime(2026, 10, 1, 7, 30),
			end_datetime=datetime(2026, 10, 1, 17, 0),
		)
		return _build_day_record(
			employee=frappe._dict(
				name="HR-EMP-0001",
				company="Test",
				date_of_joining=date(2020, 1, 1),
				default_shift="Hành chính",
			),
			work_date=date(2026, 10, 1),
			window=window,
			planned_logs=[frappe._dict(name="IN", time=datetime(2026, 10, 1, 7, 25))],
			outside_logs=[],
			holiday_context=frappe._dict(company_lists={}, holidays={}),
			attendance=None,
			leave=None,
			confirmation=frappe._dict(
				parent="VNT-AC-0001",
				issue_code="MISSING_OUT",
				issue_type="Thiếu giờ ra",
				decision_question="Có công nhận đủ ngày công không?",
				confirm="",
				evidence_code="",
			),
			can_open_confirmation=can_open_confirmation,
			effective_end=date(2026, 10, 31),
		)

	def test_day_record_links_to_the_confirmation_document_for_hr(self):
		day = self._missing_out_day(True)
		self.assertEqual(day.review_state, "pending")
		self.assertEqual(day.confirmation_name, "VNT-AC-0001")

	def test_day_record_hides_the_confirmation_document_without_permission(self):
		day = self._missing_out_day(False)
		self.assertEqual(day.review_state, "pending")
		self.assertIsNone(day.confirmation_name)

	def test_one_confirmation_per_period_is_opened_from_the_employee_name(self):
		confirmation_map = {
			("HR-EMP-0001", date(2026, 10, 1)): frappe._dict(parent="VNT-AC-0001"),
			("HR-EMP-0001", date(2026, 10, 9)): frappe._dict(parent="VNT-AC-0001"),
		}
		self.assertEqual(
			_period_confirmation_documents(confirmation_map),
			{"HR-EMP-0001": "VNT-AC-0001"},
		)

	def test_several_confirmations_fall_back_to_the_filtered_list(self):
		confirmation_map = {
			("HR-EMP-0001", date(2026, 10, 1)): frappe._dict(parent="VNT-AC-0001"),
			("HR-EMP-0001", date(2026, 10, 9)): frappe._dict(parent="VNT-AC-0002"),
			("HR-EMP-0002", date(2026, 10, 9)): frappe._dict(parent="VNT-AC-0003"),
		}
		documents = _period_confirmation_documents(confirmation_map)
		self.assertIsNone(documents["HR-EMP-0001"])
		self.assertEqual(documents["HR-EMP-0002"], "VNT-AC-0003")

	def test_monthly_excel_sheets_start_with_the_employee_code(self):
		context = frappe._dict(
			from_date=date(2026, 10, 1),
			to_date=date(2026, 10, 31),
			days=[date(2026, 10, day) for day in range(1, 32)],
			rows=[],
		)
		sheet = make_attendance_workbook(context).active
		self.assertEqual(
			[sheet.cell(1, column).value for column in (1, 2, 3)],
			["STT", "Mã nhân viên", "Tên nhân viên"],
		)
		overtime = make_overtime_workbook(context).active
		self.assertEqual(
			[overtime.cell(1, column).value for column in (1, 2, 3)],
			["Stt", "Mã nhân viên", "Tên nhân viên"],
		)

	def test_excel_formats_do_not_recreate_hidden_template_columns(self):
		days = [date(2026, 10, day) for day in range(1, 32)]
		context = frappe._dict(
			from_date=days[0],
			to_date=days[-1],
			days=days,
			rows=[],
		)
		attendance = make_attendance_workbook(context).active
		overtime = make_overtime_workbook(context).active
		self.assertEqual(attendance.max_column, 5 + 31 + len(SUMMARY_COLUMNS))
		self.assertEqual(overtime.max_column, 39)
		self.assertEqual(attendance.freeze_panes, "D4")
		self.assertFalse(any(dimension.hidden for dimension in attendance.column_dimensions.values()))
		self.assertFalse(any(dimension.hidden for dimension in overtime.column_dimensions.values()))
		self.assertEqual(overtime["AM1"].value, "Ngày lễ")
		self.assertIn("D1:E2", {str(item) for item in attendance.merged_cells.ranges})
		self.assertNotIn(
			"Ten nhan vien",
			[attendance.cell(1, column).value for column in range(1, attendance.max_column + 1)],
		)
		self.assertIn("D1:E2", {str(item) for item in overtime.merged_cells.ranges})
		self.assertIn("F1:AI1", {str(item) for item in overtime.merged_cells.ranges})
		self.assertEqual(attendance.cell(attendance.max_row, 1).value, "PHẠM NGỌC BÌNH")
		self.assertEqual(overtime.cell(overtime.max_row, 1).value, "PHẠM NGỌC BÌNH")

