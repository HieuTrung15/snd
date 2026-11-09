from datetime import datetime
from unittest import TestCase
from unittest.mock import patch

import frappe

from vinatex.vnt_hr.report.tổng_hợp_chấm_công_tháng import monthly_symbols
from vinatex.vnt_hr.report.tổng_hợp_chấm_công_tháng.monthly_symbols import (
	_apply_totals,
	_build_confirmation_review,
	_combine_with_outside,
	_confirmation_applies,
	_new_row,
	get_legend,
	_get_symbol,
	_outside_evidence_symbol,
	_symbol_after_confirmation,
)
from vinatex.vnt_hr.shift_management.work_schedule_filter import (
	ADMINISTRATIVE_FILTER,
	SHIFT_FILTER,
	SPECIAL_SHIFT_FILTER,
	get_work_schedule_filter_value,
)


def _log(hour):
	return frappe._dict(time=datetime(2026, 10, 7, hour), log_type="")


def _totals_row():
	return {
		"tot_present": 0,
		"tot_late": 0,
		"tot_early": 0,
		"tot_missing_in": 0,
		"tot_missing_out": 0,
		"tot_absent": 0,
		"tot_overtime": 0,
		"tot_off": 0,
		"tot_pending_confirmation": 0,
		"tot_approved_confirmation": 0,
		"tot_rejected_confirmation": 0,
		"tot_incomplete_approved_time": 0,
		"tot_leave": 0,
		"tot_business_trip": 0,
		"tot_holiday": 0,
	}


class TestMonthlyAttendanceSymbols(TestCase):
	def test_legend_has_no_unstyled_svg_flash(self):
		with patch.object(monthly_symbols, "_", lambda value: value):
			legend = get_legend()
		self.assertNotIn("<svg", legend)
		self.assertNotIn("vnt-attendance-legend__toggle", legend)
		self.assertIn("vnt-attendance-legend__summary", legend)

	def test_work_schedule_filter_uses_normalized_type_before_legacy_default(self):
		self.assertEqual(
			get_work_schedule_filter_value(
				frappe._dict(
					custom_working_schedule_type="Lịch đặc biệt",
					custom_shift_group="ĐB HC-Đêm - Nghỉ T6",
					default_shift="Hành chính",
				)
			),
			SPECIAL_SHIFT_FILTER,
		)

	def test_work_schedule_filter_classifies_current_and_legacy_records(self):
		self.assertEqual(
			get_work_schedule_filter_value(
				frappe._dict(custom_working_schedule_type="Theo kíp", custom_shift_group="Kíp 2")
			),
			SHIFT_FILTER,
		)
		self.assertEqual(
			get_work_schedule_filter_value(frappe._dict(default_shift="Hành chính")),
			ADMINISTRATIVE_FILTER,
		)
		self.assertEqual(
			get_work_schedule_filter_value(frappe._dict(custom_shift_group="TT - Nghỉ T2")),
			SPECIAL_SHIFT_FILTER,
		)

	def test_outside_evidence_distinguishes_single_from_pair(self):
		self.assertEqual(_outside_evidence_symbol([_log(8)]), "+1")
		self.assertEqual(_outside_evidence_symbol([_log(8), _log(17)]), "+")

	def test_off_uses_all_punches_even_if_technically_assigned_to_window(self):
		symbol = _get_symbol(
			frappe._dict(custom_need_check=0),
			frappe._dict(),
			[_log(8)],
			[],
			None,
			None,
			{},
			"off",
		)
		self.assertEqual(symbol, "+1")

	def test_workday_outside_only_keeps_absent_and_outside_evidence(self):
		symbol = _get_symbol(
			frappe._dict(custom_need_check=0),
			frappe._dict(is_overnight=False),
			[],
			[_log(20)],
			None,
			None,
			{},
			"work",
		)
		self.assertEqual(symbol, "V/+1")

	def test_combined_symbol_preserves_old_primary_code(self):
		self.assertEqual(_combine_with_outside("KR", "+"), "KR/+")
		self.assertEqual(_combine_with_outside("KV", "+1"), "KV/+1")

	def test_combined_totals_count_primary_and_outside_once(self):
		row = _totals_row()
		_apply_totals(row, "V/+1")
		self.assertEqual(row["tot_absent"], 1)
		self.assertEqual(row["tot_overtime"], 1)

		row = _totals_row()
		_apply_totals(row, "KR/+")
		self.assertEqual(row["tot_present"], 1)
		self.assertEqual(row["tot_missing_out"], 1)
		self.assertEqual(row["tot_overtime"], 1)

	def test_pending_confirmation_does_not_finalize_present_or_absent(self):
		row = _totals_row()
		review = _build_confirmation_review(
			frappe._dict(issue_code="MISSING_OUT", evidence_code="", confirm="")
		)
		_apply_totals(row, "KR", review)
		self.assertEqual(row["tot_present"], 0)
		self.assertEqual(row["tot_absent"], 0)
		self.assertEqual(row["tot_missing_out"], 1)
		self.assertEqual(row["tot_pending_confirmation"], 1)

	def test_no_checkin_confirmation_applies_to_plain_workday_absence(self):
		review = _build_confirmation_review(
			frappe._dict(issue_code="WORKDAY_NO_CHECKIN", evidence_code="", confirm="")
		)
		self.assertTrue(_confirmation_applies("V", "work", review))
		self.assertFalse(_confirmation_applies("V/+", "work", review))

	def test_hr_approval_decides_workday_as_present(self):
		row = _totals_row()
		review = _build_confirmation_review(
			frappe._dict(
				issue_code="WORKDAY_OUTSIDE_ONLY",
				evidence_code="+",
				confirm="Đồng ý",
			)
		)
		_apply_totals(row, "V/+", review)
		self.assertEqual(row["tot_present"], 1)
		self.assertEqual(row["tot_absent"], 0)
		self.assertEqual(row["tot_approved_confirmation"], 1)

	def test_hr_rejection_decides_workday_as_absent(self):
		row = _totals_row()
		review = _build_confirmation_review(
			frappe._dict(
				issue_code="MISSING_IN",
				evidence_code="",
				confirm="Từ chối",
			)
		)
		_apply_totals(row, "KV", review)
		self.assertEqual(row["tot_present"], 0)
		self.assertEqual(row["tot_absent"], 1)
		self.assertEqual(row["tot_rejected_confirmation"], 1)

	def test_approved_single_outside_punch_is_marked_incomplete(self):
		row = _totals_row()
		review = _build_confirmation_review(
			frappe._dict(
				issue_code="OFF_WITH_CHECKIN",
				evidence_code="+1",
				confirm="Đồng ý",
			)
		)
		_apply_totals(row, "+1", review)
		self.assertEqual(review.state, "approved_incomplete")
		self.assertEqual(row["tot_present"], 0)
		self.assertEqual(row["tot_approved_confirmation"], 1)
		self.assertEqual(row["tot_incomplete_approved_time"], 1)

	def test_pending_early_exit_remains_present_and_sm(self):
		review = _build_confirmation_review(
			frappe._dict(issue_code="EARLY_EXIT", evidence_code="", confirm="")
		)
		self.assertTrue(_confirmation_applies("Sm", "work", review))
		self.assertEqual(
			_symbol_after_confirmation(
				"Sm", frappe._dict(is_overnight=False), review
			),
			"Sm",
		)
		row = _totals_row()
		_apply_totals(row, "Sm", review)
		self.assertEqual(row["tot_present"], 1)
		self.assertEqual(row["tot_early"], 1)
		self.assertEqual(row["tot_pending_confirmation"], 1)

	def test_pending_workday_overtime_keeps_normal_presence(self):
		review = _build_confirmation_review(
			frappe._dict(
				issue_code="WORKDAY_OVERTIME",
				evidence_code="+",
				confirm="",
			)
		)
		self.assertTrue(_confirmation_applies("X/+", "work", review))
		row = _totals_row()
		_apply_totals(row, "X/+", review)
		self.assertEqual(row["tot_present"], 1)
		self.assertEqual(row["tot_overtime"], 1)
		self.assertEqual(row["tot_pending_confirmation"], 1)
		self.assertEqual(row["tot_absent"], 0)

	def test_approved_early_exit_becomes_on_time(self):
		review = _build_confirmation_review(
			frappe._dict(issue_code="EARLY_EXIT", evidence_code="", confirm="Đồng ý")
		)
		self.assertEqual(
			_symbol_after_confirmation(
				"Sm", frappe._dict(is_overnight=False), review
			),
			"X",
		)
		self.assertEqual(
			_symbol_after_confirmation(
				"Tr/Sm", frappe._dict(is_overnight=False), review
			),
			"Tr",
		)
		row = _totals_row()
		_apply_totals(row, "Sm", review)
		self.assertEqual(row["tot_present"], 1)
		self.assertEqual(row["tot_early"], 0)
		self.assertEqual(row["tot_approved_confirmation"], 1)

	def test_rejected_early_exit_stays_present_and_sm(self):
		review = _build_confirmation_review(
			frappe._dict(issue_code="EARLY_EXIT", evidence_code="", confirm="Từ chối")
		)
		self.assertEqual(
			_symbol_after_confirmation(
				"Sm", frappe._dict(is_overnight=False), review
			),
			"Sm",
		)
		row = _totals_row()
		_apply_totals(row, "Sm", review)
		self.assertEqual(row["tot_present"], 1)
		self.assertEqual(row["tot_early"], 1)
		self.assertEqual(row["tot_absent"], 0)
		self.assertEqual(row["tot_rejected_confirmation"], 1)

	def test_employee_code_follows_app_wide_precedence(self):
		self.assertEqual(
			_new_row(
				frappe._dict(
					name="HR-EMP-00001",
					employee_name="Lê Ngọc Thanh",
					custom_employee_code="NV001",
					employee_number="9999",
					attendance_device_id="55",
				)
			)["employee_code"],
			"NV001",
		)
		self.assertEqual(
			_new_row(
				frappe._dict(
					name="HR-EMP-00002",
					employee_name="Bùi Ngọc An",
					employee_number="9999",
					attendance_device_id="55",
				)
			)["employee_code"],
			"9999",
		)

	def test_employee_code_falls_back_to_employee_id(self):
		row = _new_row(frappe._dict(name="HR-EMP-00003", employee_name="Đỗ Mạnh Hùng"))
		self.assertEqual(row["employee_code"], "HR-EMP-00003")
		self.assertEqual(row["employee"], "HR-EMP-00003")

	def test_pending_review_label_states_what_hr_must_decide(self):
		review = _build_confirmation_review(
			frappe._dict(
				issue_code="MISSING_OUT",
				issue_type="Chỉ có giờ vào hợp lệ trong ca",
				decision_question="Xác nhận nhân sự có thực sự đi làm và bị thiếu giờ ra?",
				evidence_code="",
				confirm="",
			)
		)
		self.assertEqual(review.state, "pending")
		self.assertEqual(
			review.label.split("\n"),
			[
				"Chờ HR xác nhận",
				"Trường hợp: Chỉ có giờ vào hợp lệ trong ca",
				"HR cần xác nhận: Xác nhận nhân sự có thực sự đi làm và bị thiếu giờ ra?",
			],
		)

	def test_decided_review_label_drops_the_question(self):
		review = _build_confirmation_review(
			frappe._dict(
				issue_code="EARLY_EXIT",
				issue_type="Về sớm so với ca kế hoạch",
				decision_question="Xác nhận có căn cứ hợp lệ để công nhận đủ công?",
				evidence_code="",
				confirm="Đồng ý",
			)
		)
		self.assertEqual(
			review.label.split("\n"),
			["HR đồng ý: chuyển Sm thành X", "Trường hợp: Về sớm so với ca kế hoạch"],
		)

	def test_review_no_longer_links_to_a_confirmation_document(self):
		review = _build_confirmation_review(
			frappe._dict(parent="VNT-AC-0001", issue_code="MISSING_IN", evidence_code="", confirm="")
		)
		self.assertIsNone(review.get("document_name"))
		self.assertEqual(review.label, "Chờ HR xác nhận")
