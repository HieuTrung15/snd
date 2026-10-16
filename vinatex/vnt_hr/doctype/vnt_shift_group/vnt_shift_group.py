# Copyright (c) 2026, Vinatex and contributors
# License: MIT. See LICENSE

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from vinatex.vnt_hr.shift_management.constants import WEEKDAY_SEQUENCE, WEEKDAYS


class VNTShiftGroup(Document):
	"""Master for one rotating factory crew and its explicit weekly schedule."""

	def validate(self):
		self.validate_effective_dates()
		self.validate_schedule()
		self.protect_used_schedule()

	def validate_effective_dates(self):
		if self.effective_from and self.effective_to:
			if getdate(self.effective_from) > getdate(self.effective_to):
				frappe.throw(_("Effective From cannot be after Effective To."))

	def validate_schedule(self):
		seen_days: set[str] = set()
		for row in self.schedule:
			if row.day_of_week not in WEEKDAYS:
				frappe.throw(_("Invalid weekday in row {0}: {1}").format(row.idx, row.day_of_week))
			if row.day_of_week in seen_days:
				frappe.throw(_("Weekday {0} appears more than once.").format(row.day_of_week))
			seen_days.add(row.day_of_week)

			if row.is_off and row.shift_type:
				frappe.throw(_("OFF day {0} must not have a Shift Type.").format(row.day_of_week))
			if not row.is_off and not row.shift_type:
				frappe.throw(_("Working day {0} requires a Shift Type.").format(row.day_of_week))
			if row.shift_type and not frappe.db.exists("Shift Type", row.shift_type):
				frappe.throw(_("Shift Type {0} does not exist.").format(row.shift_type))

			# Sequence is derived from one centralized weekday mapping. It is stored
			# only to keep the child table predictable for HR users and exports.
			row.sequence = WEEKDAY_SEQUENCE[row.day_of_week]

		missing_days = [day for day in WEEKDAYS if day not in seen_days]
		if missing_days:
			frappe.throw(_("Weekly schedule is missing: {0}").format(", ".join(missing_days)))

	def protect_used_schedule(self):
		"""Do not reinterpret generated history by editing its source schedule."""
		if self.is_new():
			return
		previous = self.get_doc_before_save()
		if not previous:
			return

		business_changed = any(
			self.get(field) != previous.get(field) for field in ("company", "effective_from", "effective_to")
		)
		old_schedule = sorted(
			(row.day_of_week, row.shift_type, bool(row.is_off)) for row in previous.schedule
		)
		new_schedule = sorted((row.day_of_week, row.shift_type, bool(row.is_off)) for row in self.schedule)
		if not business_changed and old_schedule == new_schedule:
			return

		if frappe.get_meta("Shift Assignment").has_field("custom_shift_group") and frappe.db.exists(
			"Shift Assignment",
			{"custom_shift_group": self.name, "docstatus": ["<", 2]},
		):
			frappe.throw(
				_(
					"This Shift Group has generated Shift Assignments. "
					"Do not change its historical schedule; create a new effective-dated group instead."
				)
			)
