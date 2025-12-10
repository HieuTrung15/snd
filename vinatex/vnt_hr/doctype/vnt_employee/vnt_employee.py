# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt
import frappe
from frappe import _, scrub, throw
from frappe.model.naming import set_name_by_naming_series
from frappe.permissions import (
	add_user_permission,
	get_doc_permissions,
	has_permission,
	remove_user_permission,
)
from frappe.utils import cstr, getdate, today, validate_email_address
from frappe.utils.nestedset import NestedSet

from erpnext.utilities.transaction_base import delete_events


class VNTEmployee(NestedSet):
	def validate(self):
		from erpnext.controllers.status_updater import validate_status

		validate_status(self.status, ["Active", "Inactive", "Suspended", "Left"])
		self.set_employee_name()
		self._validate_contract_terms()

	def set_employee_name(self):
		self.employee_name = " ".join(
			filter(lambda x: x, [self.first_name, self.middle_name, self.last_name])
		)

	def _validate_contract_terms(self):
		"""Ensure contract_term in child contracts is an integer when provided."""
		for row in self.get("custom_vnt_contract") or []:
			val = row.get("contract_term")
			if val in (None, ""):
				continue
			try:
				int(str(val))
			except (ValueError, TypeError):
				frappe.throw(
					_("Dòng {0}: Thời hạn HĐ phải là số nguyên.").format(row.idx),
					title=_("Lỗi dữ liệu"),
				)
