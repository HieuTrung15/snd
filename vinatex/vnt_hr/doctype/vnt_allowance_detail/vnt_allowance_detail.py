# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class VNTAllowanceDetail(Document):
	def on_update(self):
		self._sync_employee_allowances()

	def on_trash(self):
		self._clear_employee_allowances()

	def _sync_employee_allowances(self):
		"""Push allowance detail rows into each employee's custom_phu_cap table."""
		self._ensure_allowance_tracking_columns()
		self._clear_employee_allowances()

		items = [row for row in self.items if row.employee and row.type]
		if not items:
			return

		employee_docs = {}

		for item in items:
			try:
				employee_doc = employee_docs.setdefault(
					item.employee, frappe.get_doc("Employee", item.employee)
				)
			except frappe.DoesNotExistError:
				frappe.throw(
					title="Employee not found",
					msg=f"Employee {item.employee} referenced in allowance detail {item.name} does not exist.",
				)

			child_row = employee_doc.append("custom_phu_cap", {})
			child_row.type = item.type
			child_row.he_so = item.he_so
			child_row.so_tien_phu_cap = item.so_tien_phu_cap
			child_row.from_date = item.from_date
			child_row.to_date = item.to_date
			child_row.allowance_detail = self.name
			child_row.allowance_detail_item = item.name

		for employee_doc in employee_docs.values():
			employee_doc.save(ignore_permissions=True)

	def _clear_employee_allowances(self):
		self._ensure_allowance_tracking_columns()
		allowance_rows = frappe.db.get_all(
			"VNT Employee Allowance Type",
			filters={"allowance_detail": self.name},
			pluck="name",
		)
		if allowance_rows:
			frappe.db.delete("VNT Employee Allowance Type", {"name": ("in", allowance_rows)})

	def _ensure_allowance_tracking_columns(self):
		flag = "vnt_allowance_tracking_fields_ready"
		if frappe.flags.get(flag):
			return

		table = "VNT Employee Allowance Type"
		missing = [
			field
			for field in ("allowance_detail", "allowance_detail_item")
			if not frappe.db.has_column(table, field)
		]

		if missing:
			frappe.reload_doc("vnt_hr", "doctype", "vnt_employee_allowance_type")

		# mark as ready only if both columns truly exist after reload
		if all(frappe.db.has_column(table, field) for field in ("allowance_detail", "allowance_detail_item")):
			frappe.flags[flag] = True
