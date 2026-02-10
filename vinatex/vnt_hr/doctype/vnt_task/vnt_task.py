# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate


class VNTTask(Document):
	def validate(self):
		self._sync_department_from_employee()
		item_meta = self._sync_from_kpi_item()
		self._validate_dates(item_meta)

	def _sync_department_from_employee(self):
		if not self.employee or self.department:
			return

		employee_department = frappe.db.get_value("Employee", self.employee, "department")
		if employee_department:
			self.department = employee_department

	def _sync_from_kpi_item(self):
		if not self.kpi_cv_item:
			return None

		item = frappe.db.get_value(
			"VNT KPI Chuyen Vien Item",
			self.kpi_cv_item,
			["name", "parent", "parenttype", "date"],
			as_dict=True,
		)

		if not item:
			frappe.throw(_("KPI Chuyên viên item không tồn tại: {0}.").format(self.kpi_cv_item))

		if item.parenttype != "VNT KPI Chuyen Vien":
			frappe.throw(_("KPI Chuyên viên item không hợp lệ: {0}.").format(self.kpi_cv_item))

		parent = frappe.db.get_value(
			"VNT KPI Chuyen Vien",
			item.parent,
			["emp_chuyenvien", "department"],
			as_dict=True,
		)

		if parent:
			if parent.get("emp_chuyenvien") and not self.employee:
				self.employee = parent.emp_chuyenvien
			if parent.get("department") and not self.department:
				self.department = parent.department

		return item

	def _validate_dates(self, item_meta):
		start_date = getdate(self.exp_start_date) if self.exp_start_date else None
		end_date = getdate(self.exp_end_date) if self.exp_end_date else None
		deadline = getdate(self.deadline) if self.deadline else None

		if self.kpi_cv_item:
			if not start_date:
				frappe.throw(_("Vui lòng nhập ngày bắt đầu dự kiến."))
			if deadline:
				if not end_date or end_date != deadline:
					self.exp_end_date = deadline
					end_date = deadline
				if start_date.year != deadline.year or start_date.month != deadline.month:
					frappe.throw(_("Ngày bắt đầu và thời hạn phải nằm trong cùng một tháng."))

		if start_date and end_date and start_date > end_date:
			frappe.throw(_("Ngày bắt đầu dự kiến không thể lớn hơn ngày kết thúc dự kiến."))

		if not item_meta or not item_meta.get("date"):
			return

		item_deadline = getdate(item_meta.date)

		if deadline and deadline > item_deadline:
			frappe.throw(
				_("Deadline task không được muộn hơn hạn KPI Chuyên viên ({0}).").format(item_meta.date)
			)

		if end_date and end_date > item_deadline:
			frappe.throw(
				_("Ngày kết thúc dự kiến không được muộn hơn hạn KPI Chuyên viên ({0}).").format(
					item_meta.date
				)
			)
