from unittest import TestCase

import frappe

from vinatex.vinatex.doctype.overrides.employee import VntEmployee


class _EmployeeFixture:
	def __init__(self, current_group=None, previous_group=None, *, has_previous=True):
		self.current_group = current_group
		self.previous = (
			frappe._dict(custom_shift_group=previous_group) if has_previous else None
		)

	def get_doc_before_save(self):
		return self.previous

	def get(self, fieldname):
		if fieldname == "custom_shift_group":
			return self.current_group
		return None


class TestEmployeeShiftGroupGuard(TestCase):
	def test_existing_employee_cannot_save_changed_shift_group_directly(self):
		employee = _EmployeeFixture(current_group="3", previous_group="4")

		with self.assertRaisesRegex(frappe.ValidationError, "ngày hiệu lực"):
			VntEmployee._validate_shift_group_change_uses_transfer_workflow(employee)

	def test_unchanged_shift_group_is_allowed(self):
		employee = _EmployeeFixture(current_group="4", previous_group="4")

		VntEmployee._validate_shift_group_change_uses_transfer_workflow(employee)

	def test_new_employee_without_shift_group_is_allowed(self):
		employee = _EmployeeFixture(current_group=None, has_previous=False)

		VntEmployee._validate_shift_group_change_uses_transfer_workflow(employee)
