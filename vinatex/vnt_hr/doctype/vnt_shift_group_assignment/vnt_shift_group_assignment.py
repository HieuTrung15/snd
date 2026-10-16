# Copyright (c) 2026, Vinatex and contributors
# License: MIT. See LICENSE

from __future__ import annotations

from datetime import date

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class VNTShiftGroupAssignment(Document):
	"""Effective-dated history of an Employee's rotating shift group."""

	def validate(self):
		self.validate_dates()
		self.validate_company()
		self.validate_group_effective_period()
		self.validate_no_overlap()
		self.protect_attendance_history()

	def on_trash(self):
		if self._get_usage_dates(self):
			frappe.throw(
				_(
					"This Shift Group Assignment already has planned/final attendance data and must not be deleted."
				)
			)

	def validate_dates(self):
		if self.to_date and getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(_("From Date cannot be after To Date."))

	def validate_company(self):
		employee_company = frappe.db.get_value("Employee", self.employee, "company")
		group_company = frappe.db.get_value("VNT Shift Group", self.shift_group, "company")
		if not employee_company or not group_company:
			frappe.throw(_("Employee and Shift Group must have a Company."))
		if self.company != employee_company or self.company != group_company:
			frappe.throw(_("Employee, assignment and Shift Group must belong to the same Company."))

	def validate_group_effective_period(self):
		group = frappe.db.get_value(
			"VNT Shift Group",
			self.shift_group,
			["effective_from", "effective_to", "disabled"],
			as_dict=True,
		)
		if not group:
			return
		if group.disabled and self.status == "Active":
			frappe.throw(_("Cannot create an active assignment for a disabled Shift Group."))
		if group.effective_from and getdate(self.from_date) < getdate(group.effective_from):
			frappe.throw(_("Assignment starts before the Shift Group effective period."))
		if group.effective_to and (not self.to_date or getdate(self.to_date) > getdate(group.effective_to)):
			frappe.throw(_("Assignment ends after the Shift Group effective period."))

	def validate_no_overlap(self):
		if self.status != "Active":
			return

		# Serialize effective-dated membership changes per Employee. Locking only
		# matching assignment rows would not protect the first concurrent insert.
		employee = frappe.qb.DocType("Employee")
		(
			frappe.qb.from_(employee).select(employee.name).where(employee.name == self.employee).for_update()
		).run()

		assignment = frappe.qb.DocType("VNT Shift Group Assignment")
		upper_bound = getdate(self.to_date) if self.to_date else date.max
		query = (
			frappe.qb.from_(assignment)
			.select(assignment.name)
			.where(
				(assignment.employee == self.employee)
				& (assignment.status == "Active")
				& (assignment.name != (self.name or ""))
				& (assignment.from_date <= upper_bound)
				& (assignment.to_date.isnull() | (assignment.to_date >= self.from_date))
			)
			.for_update()
		)
		overlap = query.run(pluck=True)
		if overlap:
			frappe.throw(
				_("Employee already has an overlapping active Shift Group Assignment: {0}").format(
					frappe.get_desk_link("VNT Shift Group Assignment", overlap[0])
				)
			)

	def protect_attendance_history(self):
		"""Block edits that would reinterpret a period with final Attendance.

		The record remains editable for notes and safe future end-date changes, but
		business keys/history cannot be rewritten after Attendance exists.
		"""
		if self.is_new():
			return

		previous = self.get_doc_before_save()
		if not previous:
			return

		business_fields = ("employee", "company", "shift_group", "from_date", "status")
		business_changed = any(self.get(field) != previous.get(field) for field in business_fields)
		end_date_shortened = bool(
			self.to_date and (not previous.to_date or getdate(self.to_date) < getdate(previous.to_date))
		)
		if not business_changed and not end_date_shortened:
			return

		usage_dates = self._get_usage_dates(previous)
		if not usage_dates:
			return

		if business_changed or max(usage_dates) > getdate(self.to_date):
			frappe.throw(
				_(
					"This Shift Group Assignment is already used by Shift Assignment or Attendance. "
					"Close history without changing its business meaning and create a new assignment."
				)
			)

	def _get_usage_dates(self, assignment):
		filters = {
			"employee": assignment.employee,
			"attendance_date": [">=", assignment.from_date],
			"docstatus": ["<", 2],
		}
		if assignment.to_date:
			filters["attendance_date"] = ["between", [assignment.from_date, assignment.to_date]]
		attendance_dates = frappe.get_all("Attendance", filters=filters, pluck="attendance_date")

		planned_dates = []
		if frappe.get_meta("Shift Assignment").has_field("custom_shift_group"):
			shift_filters = {
				"employee": assignment.employee,
				"custom_shift_group": assignment.shift_group,
				"start_date": [">=", assignment.from_date],
				"docstatus": ["<", 2],
			}
			if assignment.to_date:
				shift_filters["start_date"] = [
					"between",
					[assignment.from_date, assignment.to_date],
				]
			planned_dates = frappe.get_all("Shift Assignment", filters=shift_filters, pluck="start_date")

		return [getdate(value) for value in attendance_dates + planned_dates]
