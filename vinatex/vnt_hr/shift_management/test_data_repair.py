from datetime import datetime, time
from unittest import TestCase
from unittest.mock import patch

import frappe

from vinatex.vnt_hr.shift_management.data_repair import (
	repair_administrative_shift_checkins,
)


def _shift_master(*, end_time=time(16, 30), before=60, after=60):
	return frappe._dict(
		name="Hành chính",
		start_time=time(7, 30),
		end_time=end_time,
		begin_check_in_before_shift_start_time=before,
		allow_check_out_after_shift_end_time=after,
	)


def _checkin(
	*,
	name="CHK-001",
	checkin_time=datetime(2026, 10, 6, 17),
	shift_start=datetime(2026, 10, 6, 7, 30),
	shift_end=datetime(2026, 10, 6, 17),
	shift_actual_start=datetime(2026, 10, 6, 6, 30),
	shift_actual_end=datetime(2026, 10, 6, 18),
	offshift=0,
	attendance="ATT-001",
):
	return frappe._dict(
		name=name,
		time=checkin_time,
		shift_start=shift_start,
		shift_end=shift_end,
		shift_actual_start=shift_actual_start,
		shift_actual_end=shift_actual_end,
		offshift=offshift,
		attendance=attendance,
	)


class TestAdministrativeShiftCheckinRepair(TestCase):
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.db.set_value")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_all")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_cached_doc")
	def test_dry_run_reports_linked_old_metadata_without_writing(
		self, get_cached_doc, get_all, set_value
	):
		get_cached_doc.return_value = _shift_master()
		get_all.return_value = [_checkin()]

		result = repair_administrative_shift_checkins(dry_run=True)

		self.assertEqual(result["rows_to_update"], 1)
		self.assertEqual(result["linked_rows"], 1)
		self.assertEqual(result["updated_rows"], 0)
		set_value.assert_not_called()

	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.db.set_value")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_all")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_cached_doc")
	def test_execute_updates_only_shift_metadata_and_preserves_modified(
		self, get_cached_doc, get_all, set_value
	):
		get_cached_doc.return_value = _shift_master()
		get_all.return_value = [_checkin()]

		result = repair_administrative_shift_checkins(dry_run=False)

		values = set_value.call_args.args[2]
		self.assertEqual(
			set(values),
			{"shift_start", "shift_end", "shift_actual_start", "shift_actual_end", "offshift"},
		)
		self.assertEqual(values["shift_start"], datetime(2026, 10, 6, 7, 30))
		self.assertEqual(values["shift_end"], datetime(2026, 10, 6, 16, 30))
		self.assertEqual(values["shift_actual_start"], datetime(2026, 10, 6, 6, 30))
		self.assertEqual(values["shift_actual_end"], datetime(2026, 10, 6, 17, 30))
		self.assertEqual(values["offshift"], 0)
		self.assertFalse(set_value.call_args.kwargs["update_modified"])
		self.assertEqual(result["updated_rows"], 1)

	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.db.set_value")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_all")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_cached_doc")
	def test_query_starts_at_effective_date_and_excludes_cancelled_rows(
		self, get_cached_doc, get_all, _set_value
	):
		get_cached_doc.return_value = _shift_master()
		get_all.return_value = []

		repair_administrative_shift_checkins(effective_from="2026-10-01", dry_run=True)

		filters = get_all.call_args.kwargs["filters"]
		self.assertEqual(filters["shift"], "Hành chính")
		self.assertEqual(filters["time"], [">=", datetime(2026, 10, 1)])
		self.assertEqual(filters["docstatus"], ["<", 2])

	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.db.set_value")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_all")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_cached_doc")
	def test_missing_shift_start_uses_checkin_calendar_date(
		self, get_cached_doc, get_all, set_value
	):
		get_cached_doc.return_value = _shift_master()
		get_all.return_value = [
			_checkin(
				checkin_time=datetime(2026, 10, 7, 17),
				shift_start=None,
				shift_end=None,
				shift_actual_start=None,
				shift_actual_end=None,
			)
		]

		repair_administrative_shift_checkins(dry_run=False)

		values = set_value.call_args.args[2]
		self.assertEqual(values["shift_start"], datetime(2026, 10, 7, 7, 30))

	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.db.set_value")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_all")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_cached_doc")
	def test_existing_shift_start_date_wins_over_checkin_time_date(
		self, get_cached_doc, get_all, set_value
	):
		get_cached_doc.return_value = _shift_master()
		get_all.return_value = [
			_checkin(
				checkin_time=datetime(2026, 10, 7, 0, 10),
				shift_start=datetime(2026, 10, 6, 7, 30),
			)
		]

		repair_administrative_shift_checkins(dry_run=False)

		values = set_value.call_args.args[2]
		self.assertEqual(values["shift_start"], datetime(2026, 10, 6, 7, 30))

	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.db.set_value")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_all")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_cached_doc")
	def test_wrong_shift_master_aborts_before_query_or_write(
		self, get_cached_doc, get_all, set_value
	):
		get_cached_doc.return_value = _shift_master(end_time=time(17))

		with self.assertRaises(frappe.ValidationError):
			repair_administrative_shift_checkins(dry_run=False)

		self.assertFalse(
			any(call.args and call.args[0] == "Employee Checkin" for call in get_all.call_args_list)
		)
		set_value.assert_not_called()

	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.db.set_value")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_all")
	@patch("vinatex.vnt_hr.shift_management.data_repair.frappe.get_cached_doc")
	def test_already_correct_rows_are_idempotent(
		self, get_cached_doc, get_all, set_value
	):
		get_cached_doc.return_value = _shift_master()
		get_all.return_value = [
			_checkin(
				shift_end=datetime(2026, 10, 6, 16, 30),
				shift_actual_end=datetime(2026, 10, 6, 17, 30),
			)
		]

		result = repair_administrative_shift_checkins(dry_run=False)

		self.assertEqual(result["rows_to_update"], 0)
		self.assertEqual(result["already_correct"], 1)
		self.assertEqual(result["updated_rows"], 0)
		set_value.assert_not_called()
