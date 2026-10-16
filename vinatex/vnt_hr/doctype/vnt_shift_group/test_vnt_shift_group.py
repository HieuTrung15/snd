# Copyright (c) 2026, Vinatex and contributors
# License: MIT. See LICENSE

from __future__ import annotations

from datetime import datetime, time

import frappe
from erpnext.setup.doctype.employee.test_employee import make_employee
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from vinatex.vnt_hr.shift_management.constants import DEFAULT_SHIFT_GROUP_MATRIX, WEEKDAYS
from vinatex.vnt_hr.shift_management.holiday_service import sync_shift_group_holiday_list
from vinatex.vnt_hr.shift_management.setup import _inspect_shift_type_mapping
from vinatex.vnt_hr.shift_management.shift_assignment_service import generate_shift_assignments
from vinatex.vnt_hr.shift_management.shift_group_service import (
	get_employee_shift_group,
	get_work_date_for_checkin,
)
from vinatex.vnt_hr.shift_management.shift_group_transfer_service import (
	_run_bulk_shift_group_transfer,
	preview_bulk_shift_group_transfer,
)


class TestVNTShiftGroupMatrix(FrappeTestCase):
	"""Fast business-rule tests for the approved seven-crew matrix."""

	def test_01_group_1_monday_is_afternoon(self):
		self.assertEqual(DEFAULT_SHIFT_GROUP_MATRIX["Kíp 1"][0], "afternoon")

	def test_02_group_1_friday_is_off(self):
		self.assertIsNone(DEFAULT_SHIFT_GROUP_MATRIX["Kíp 1"][4])

	def test_03_group_2_thursday_is_off(self):
		self.assertIsNone(DEFAULT_SHIFT_GROUP_MATRIX["Kíp 2"][3])

	def test_04_group_3_monday_is_night(self):
		self.assertEqual(DEFAULT_SHIFT_GROUP_MATRIX["Kíp 3"][0], "night")

	def test_05_group_4_tuesday_is_off(self):
		self.assertIsNone(DEFAULT_SHIFT_GROUP_MATRIX["Kíp 4"][1])

	def test_06_group_5_monday_is_off(self):
		self.assertIsNone(DEFAULT_SHIFT_GROUP_MATRIX["Kíp 5"][0])

	def test_07_group_6_sunday_is_off(self):
		self.assertIsNone(DEFAULT_SHIFT_GROUP_MATRIX["Kíp 6"][6])

	def test_08_group_7_saturday_is_off(self):
		self.assertIsNone(DEFAULT_SHIFT_GROUP_MATRIX["Kíp 7"][5])

	def test_16_night_shift_uses_start_date_as_work_date(self):
		work_date = get_work_date_for_checkin(
			datetime(2026, 10, 6, 2, 0),
			shift_start_time=time(22, 0),
			shift_end_time=time(6, 0),
		)
		self.assertEqual(work_date, getdate("2026-10-05"))


class TestVNTShiftGroupIntegration(FrappeTestCase):
	"""Integration coverage; run only on a dedicated Frappe test database."""

	def setUp(self):
		self.company = "_Test Company"
		self.start_date = getdate("2026-10-05")  # Monday
		self.shift_names = {
			"morning": "_VNT Test Morning",
			"afternoon": "_VNT Test Afternoon",
			"night": "_VNT Test Night",
			"administrative": "_VNT Test Administrative",
		}
		self._make_shift_type(self.shift_names["morning"], "06:00:00", "14:00:00")
		self._make_shift_type(self.shift_names["afternoon"], "14:00:00", "22:00:00")
		self._make_shift_type(self.shift_names["night"], "22:00:00", "06:00:00")
		self._make_shift_type(self.shift_names["administrative"], "07:30:00", "16:30:00")
		self.group_1 = self._make_group("_VNT Test Group 1", DEFAULT_SHIFT_GROUP_MATRIX["Kíp 1"])
		self.group_2 = self._make_group("_VNT Test Group 2", DEFAULT_SHIFT_GROUP_MATRIX["Kíp 2"])
		self.group_3 = self._make_group("_VNT Test Group 3", DEFAULT_SHIFT_GROUP_MATRIX["Kíp 3"])
		self.employee = make_employee("vnt-shift-engine@example.com", company=self.company)

	def test_09_sixty_day_generation_has_no_duplicates(self):
		self._set_custom_group(self.group_1)
		result = generate_shift_assignments(
			self.start_date, add_days(self.start_date, 59), employees=[self.employee]
		)
		created = result["counts"].get("CREATE", 0)
		self.assertGreater(created, 0)
		self.assertEqual(
			frappe.db.count(
				"Shift Assignment",
				{"employee": self.employee, "custom_generated_by_shift_group": 1},
			),
			created,
		)

	def test_10_second_generator_run_is_idempotent(self):
		self._set_custom_group(self.group_1)
		first = generate_shift_assignments(
			self.start_date, add_days(self.start_date, 6), employees=[self.employee]
		)
		second = generate_shift_assignments(
			self.start_date, add_days(self.start_date, 6), employees=[self.employee]
		)
		self.assertGreater(first["counts"].get("CREATE", 0), 0)
		self.assertEqual(second["counts"].get("CREATE", 0), 0)
		self.assertGreater(second["counts"].get("SKIP_EXISTING", 0), 0)

	def test_10b_expired_inactive_assignment_is_still_idempotent(self):
		"""HRMS marks expired assignments Inactive; a backfill must not recreate them."""
		self._set_custom_group(self.group_1)
		first = generate_shift_assignments(
			self.start_date, add_days(self.start_date, 6), employees=[self.employee]
		)
		assignment_names = frappe.get_all(
			"Shift Assignment",
			filters={
				"employee": self.employee,
				"docstatus": 1,
				"custom_generated_by_shift_group": 1,
				"start_date": ["between", [self.start_date, add_days(self.start_date, 6)]],
			},
			pluck="name",
		)
		for assignment_name in assignment_names:
			frappe.db.set_value(
				"Shift Assignment", assignment_name, "status", "Inactive", update_modified=False
			)

		second = generate_shift_assignments(
			self.start_date, add_days(self.start_date, 6), employees=[self.employee]
		)

		self.assertGreater(first["counts"].get("CREATE", 0), 0)
		self.assertEqual(second["counts"].get("CREATE", 0), 0)
		self.assertEqual(
			frappe.db.count(
				"Shift Assignment",
				{
					"employee": self.employee,
					"docstatus": ["<", 2],
					"custom_generated_by_shift_group": 1,
					"start_date": ["between", [self.start_date, add_days(self.start_date, 6)]],
				},
			),
			len(assignment_names),
		)

	def test_11_manual_shift_assignment_is_not_overwritten(self):
		self._set_custom_group(self.group_1)
		manual = self._make_shift_assignment(
			self.employee,
			self.shift_names["night"],
			self.start_date,
			"Đổi ca",
		)
		result = generate_shift_assignments(self.start_date, self.start_date, employees=[self.employee])
		manual.reload()
		self.assertEqual(result["counts"].get("SKIP_MANUAL"), 1)
		self.assertEqual(manual.shift_type, self.shift_names["night"])

	def test_12_effective_assignment_precedes_employee_custom_group(self):
		self._set_custom_group(self.group_2)
		self._make_group_assignment(self.group_3)
		resolved = get_employee_shift_group(self.employee, self.start_date)
		self.assertEqual(resolved.shift_group, self.group_3)
		self.assertEqual(resolved.source, "VNT Shift Group Assignment")

	def test_13_employee_custom_group_is_used_without_assignment(self):
		self._set_custom_group(self.group_2)
		resolved = get_employee_shift_group(self.employee, self.start_date)
		self.assertEqual(resolved.shift_group, self.group_2)
		self.assertEqual(resolved.source, "Employee.custom_shift_group")

	def test_14_legacy_default_shift_is_read_only(self):
		legacy_name = "_VNT Test Legacy Group"
		self._make_shift_type(legacy_name, "08:00:00", "09:00:00")
		self._make_group(legacy_name, DEFAULT_SHIFT_GROUP_MATRIX["Kíp 2"])
		frappe.db.set_value("Employee", self.employee, "custom_shift_group", None, update_modified=False)
		frappe.db.set_value("Employee", self.employee, "default_shift", legacy_name, update_modified=False)
		modified_before = frappe.db.get_value("Employee", self.employee, "modified")
		resolved = get_employee_shift_group(self.employee, self.start_date)
		self.assertEqual(resolved.shift_group, legacy_name)
		self.assertEqual(frappe.db.get_value("Employee", self.employee, "modified"), modified_before)

	def test_15_administrative_default_shift_is_not_a_group(self):
		frappe.db.set_value("Employee", self.employee, "custom_shift_group", None, update_modified=False)
		frappe.db.set_value(
			"Employee",
			self.employee,
			"default_shift",
			self.shift_names["administrative"],
			update_modified=False,
		)
		self.assertIsNone(get_employee_shift_group(self.employee, self.start_date))

	def test_15b_custom_group_outside_effective_period_is_not_used(self):
		future_group = self._make_group(
			"_VNT Test Future Group", DEFAULT_SHIFT_GROUP_MATRIX["Kíp 1"]
		)
		group = frappe.get_doc("VNT Shift Group", future_group)
		group.effective_from = add_days(self.start_date, 1)
		group.save()
		self._set_custom_group(future_group)

		result = generate_shift_assignments(
			self.start_date, self.start_date, employees=[self.employee], preview=True
		)

		self.assertEqual(result["counts"].get("SKIP_NO_GROUP"), 1)

	def test_17_off_day_does_not_create_assignment(self):
		self._set_custom_group(self.group_1)
		friday = add_days(self.start_date, 4)
		result = generate_shift_assignments(friday, friday, employees=[self.employee])
		self.assertEqual(result["counts"].get("OFF"), 1)
		self.assertFalse(
			frappe.db.exists("Shift Assignment", {"employee": self.employee, "start_date": friday})
		)

	def test_18_existing_holiday_list_conflict_is_not_overwritten(self):
		holiday_name = "_VNT-CONFLICT-2026"
		if not frappe.db.exists("Holiday List", holiday_name):
			holiday = frappe.get_doc(
				{
					"doctype": "Holiday List",
					"holiday_list_name": holiday_name,
					"from_date": "2026-01-01",
					"to_date": "2026-12-31",
					"weekly_off": "Sunday",
					"holidays": [{"holiday_date": "2026-01-01", "description": "Existing", "weekly_off": 0}],
				}
			)
			holiday.flags.skip_vnt_global_holiday_assignment = True
			holiday.insert()
		group = frappe.get_doc("VNT Shift Group", self.group_1)
		group.holiday_list = holiday_name
		group.save()
		before = frappe.get_all("Holiday", {"parent": holiday_name}, pluck="holiday_date")
		result = sync_shift_group_holiday_list(self.group_1, 2026)
		after = frappe.get_all("Holiday", {"parent": holiday_name}, pluck="holiday_date")
		self.assertEqual(result["status"], "CONFLICT")
		self.assertEqual(before, after)

	def test_19_conflicting_shift_type_is_not_changed(self):
		conflict_name = "_VNT Test Conflict Administrative"
		self._make_shift_type(conflict_name, "07:30:00", "17:00:00")
		inspection = _inspect_shift_type_mapping({"administrative": conflict_name})
		self.assertEqual(inspection["administrative"]["status"], "CONFLICT")
		self.assertEqual(
			frappe.db.get_value("Shift Type", conflict_name, "end_time"),
			frappe.utils.get_timedelta("17:00:00"),
		)

	def test_20_overlapping_group_assignment_is_rejected(self):
		self._make_group_assignment(self.group_1)
		second = frappe.get_doc(
			{
				"doctype": "VNT Shift Group Assignment",
				"employee": self.employee,
				"company": self.company,
				"shift_group": self.group_2,
				"from_date": add_days(self.start_date, 1),
				"status": "Active",
			}
		)
		self.assertRaises(frappe.ValidationError, second.insert)

	def test_21_bulk_transfer_preview_is_read_only(self):
		transfer_date = add_days(getdate(today()), 1)
		period_end = add_days(transfer_date, 6)
		self._set_custom_group(self.group_1)
		generate_shift_assignments(transfer_date, period_end, employees=[self.employee])

		assignment_count = frappe.db.count("Shift Assignment", {"employee": self.employee, "docstatus": 1})
		membership_count = frappe.db.count("VNT Shift Group Assignment", {"employee": self.employee})
		preview = preview_bulk_shift_group_transfer(
			[self.employee],
			self.group_2,
			transfer_date,
			period_end,
			period_end,
			"Test preview only",
		)

		self.assertEqual(preview["counts"].get("READY"), 1)
		self.assertGreater(preview["auto_assignments_to_cancel"], 0)
		self.assertNotIn("assignment_names_to_cancel", preview)
		self.assertEqual(
			frappe.db.count("Shift Assignment", {"employee": self.employee, "docstatus": 1}),
			assignment_count,
		)
		self.assertEqual(
			frappe.db.count("VNT Shift Group Assignment", {"employee": self.employee}),
			membership_count,
		)

	def test_22_bulk_transfer_preserves_manual_and_regenerates_auto_assignments(self):
		transfer_date = add_days(getdate(today()), 1)
		period_end = add_days(transfer_date, 6)
		self._set_custom_group(self.group_1)
		manual = self._make_shift_assignment(
			self.employee,
			self.shift_names["night"],
			transfer_date,
			"Đổi ca",
		)
		generate_shift_assignments(add_days(transfer_date, 1), period_end, employees=[self.employee])

		result = _run_bulk_shift_group_transfer(
			{
				"employees": [self.employee],
				"target_shift_group": self.group_2,
				"effective_date": transfer_date,
				"membership_end_date": period_end,
				"generate_until": period_end,
				"note": "Test bulk transfer",
			}
		)

		manual.reload()
		self.assertEqual(result["status"], "COMPLETED")
		self.assertEqual(manual.docstatus, 1)
		self.assertEqual(manual.shift_type, self.shift_names["night"])
		self.assertEqual(
			frappe.db.get_value(
				"VNT Shift Group Assignment",
				{"employee": self.employee, "status": "Active"},
				"shift_group",
			),
			self.group_2,
		)
		self.assertEqual(
			frappe.db.get_value("Employee", self.employee, "custom_shift_group"),
			self.group_1,
		)
		active_auto_groups = set(
			frappe.get_all(
				"Shift Assignment",
				filters={
					"employee": self.employee,
					"docstatus": 1,
					"custom_generated_by_shift_group": 1,
					"start_date": ["between", [transfer_date, period_end]],
				},
				pluck="custom_shift_group",
			)
		)
		self.assertEqual(active_auto_groups, {self.group_2})

	def test_23_bulk_transfer_closes_previous_membership(self):
		transfer_date = add_days(getdate(today()), 1)
		period_end = add_days(transfer_date, 6)
		current_membership = self._make_group_assignment(self.group_1)
		generate_shift_assignments(transfer_date, period_end, employees=[self.employee])

		result = _run_bulk_shift_group_transfer(
			{
				"employees": [self.employee],
				"target_shift_group": self.group_2,
				"effective_date": transfer_date,
				"membership_end_date": period_end,
				"generate_until": period_end,
				"note": "Test membership history",
			}
		)

		current_membership.reload()
		self.assertEqual(result["membership_actions"].get("CLOSE_AND_CREATE"), 1)
		self.assertEqual(getdate(current_membership.to_date), add_days(transfer_date, -1))
		self.assertEqual(current_membership.status, "Active")
		self.assertTrue(
			frappe.db.exists(
				"VNT Shift Group Assignment",
				{
					"employee": self.employee,
					"shift_group": self.group_2,
					"from_date": transfer_date,
					"to_date": period_end,
					"status": "Active",
				},
			)
		)

	def _make_shift_type(self, name, start_time, end_time):
		if frappe.db.exists("Shift Type", name):
			return name
		frappe.get_doc(
			{
				"doctype": "Shift Type",
				"name": name,
				"start_time": start_time,
				"end_time": end_time,
				"enable_auto_attendance": 0,
			}
		).insert()
		return name

	def _make_group(self, name, matrix):
		if frappe.db.exists("VNT Shift Group", name):
			return name
		schedule = []
		for index, (weekday, role) in enumerate(zip(WEEKDAYS, matrix, strict=True), start=1):
			schedule.append(
				{
					"day_of_week": weekday,
					"shift_type": self.shift_names.get(role) if role else None,
					"is_off": 0 if role else 1,
					"sequence": index,
				}
			)
		return (
			frappe.get_doc(
				{
					"doctype": "VNT Shift Group",
					"shift_group_name": name,
					"company": self.company,
					"effective_from": "2026-01-01",
					"schedule": schedule,
				}
			)
			.insert()
			.name
		)

	def _set_custom_group(self, group):
		frappe.db.set_value("Employee", self.employee, "custom_shift_group", group, update_modified=False)

	def _make_group_assignment(self, group):
		return frappe.get_doc(
			{
				"doctype": "VNT Shift Group Assignment",
				"employee": self.employee,
				"company": self.company,
				"shift_group": group,
				"from_date": self.start_date,
				"status": "Active",
			}
		).insert()

	def _make_shift_assignment(self, employee, shift_type, work_date, source):
		doc = frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": employee,
				"shift_type": shift_type,
				"start_date": work_date,
				"end_date": work_date,
				"status": "Active",
				"custom_assignment_source": source,
			}
		)
		doc.insert()
		doc.submit()
		return doc
