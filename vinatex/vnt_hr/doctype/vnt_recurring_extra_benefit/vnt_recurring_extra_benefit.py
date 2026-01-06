# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

import re
from typing import Dict, List

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class VNTRecurringExtraBenefit(Document):
	_link_fields_present: bool | None = None

	def on_submit(self):
		self._sync_salary_slip_items(add_rows=True)

	def on_cancel(self):
		self.ignore_linked_doctypes = ("VNT Salary Slip",)
		self._sync_salary_slip_items(add_rows=False)

	@frappe.whitelist()
	def get_emp_list(self):
		"""Return employees that have the selected allowance type on their profile."""
		if not self.type:
			frappe.throw(_("Vui lòng chọn Loại phụ cấp trước khi lấy danh sách nhân sự."))

		rows = _get_employees_with_allowance(self.type)
		return {"items": rows}

	def _sync_salary_slip_items(self, add_rows: bool):
		if not self.items:
			frappe.throw(_("Vui lòng nhập ít nhất 1 dòng nhân sự trước khi submit."))

		month = self._get_target_month()
		year = self._get_target_year()
		employees = self._get_employee_codes()

		if add_rows:
			slip_map = self._fetch_salary_slips(employees, month, year)
			missing = [emp for emp in employees if emp not in slip_map]
			if missing:
				frappe.throw(
					_("Không tìm thấy VNT Salary Slip cho các nhân sự {0} (Tháng {1}/{2}).").format(
						", ".join(sorted(missing)), month, year
					)
				)
			self._insert_allowances_into_slips(slip_map)
		else:
			self._remove_allowances_from_slips(employees, month, year)

	def _get_target_month(self) -> str:
		raw_month = (self.month or "").strip()
		if not raw_month:
			frappe.throw(_("Vui lòng nhập Tháng áp dụng."))

		for token in re.findall(r"\d+", raw_month):
			try:
				month_num = int(token)
			except ValueError:
				continue
			if 1 <= month_num <= 12:
				return f"{month_num:02d}"

		frappe.throw(_("Giá trị Tháng không hợp lệ: {0}").format(raw_month))

	def _get_target_year(self) -> int:
		year_value = cint(self.year)
		if not year_value:
			frappe.throw(_("Vui lòng nhập Năm áp dụng."))
		return year_value

	def _get_employee_codes(self) -> List[str]:
		employees = {row.employee for row in (self.items or []) if row.employee}
		if not employees:
			frappe.throw(_("Vui lòng chọn Nhân sự trong bảng Chi tiết."))
		return sorted(employees)

	def _fetch_salary_slips(self, employees: List[str], month: str, year: int) -> Dict[str, str]:
		if not employees:
			return {}

		slip_rows = frappe.get_all(
			"VNT Salary Slip",
			filters={
				"employee": ("in", employees),
				"month": month,
				"year": year,
				"docstatus": ("in", [0, 1]),
			},
			fields=["name", "employee", "docstatus", "modified"],
			order_by="docstatus desc, modified desc",
		)

		slip_map: Dict[str, str] = {}
		for row in slip_rows:
			if row.employee in slip_map:
				continue
			slip_map[row.employee] = row.name
		return slip_map

	def _insert_allowances_into_slips(self, slip_map: Dict[str, str]):
		slip_cache: Dict[str, Document] = {}
		cleansed = set()
		link_updates = []

		for row in self.items:
			employee = row.employee
			if not employee:
				continue
			slip_name = slip_map.get(employee)
			if not slip_name:
				continue

			slip_doc = slip_cache.get(slip_name)
			if not slip_doc:
				slip_doc = frappe.get_doc("VNT Salary Slip", slip_name)
				slip_doc.flags.ignore_permissions = True
				slip_doc.flags.ignore_validate_update_after_submit = True
				slip_cache[slip_name] = slip_doc

			if slip_name not in cleansed:
				filtered_items = [
					child
					for child in (slip_doc.items or [])
					if getattr(child, "recurring_extra_benefit", None) != self.name
				]
				slip_doc.set("items", filtered_items)
				cleansed.add(slip_name)

			child_row = slip_doc.append("items", self._build_salary_slip_child_row(row))
			link_updates.append((row, slip_doc.name, child_row))

		for slip_doc in slip_cache.values():
			slip_doc.save(ignore_permissions=True)

		if self._link_fields_available():
			for row, slip_name, child_row in link_updates:
				self._update_parent_item_links(row, slip_name, child_row.name)

	def _remove_allowances_from_slips(self, employees: List[str], month: str, year: int):
		if self._remove_allowances_by_reference():
			if self._link_fields_available():
				for row in (self.items or []):
					self._clear_parent_item_links(row)
			return

		rows_with_links = []
		if self._link_fields_available():
			rows_with_links = [
				row
				for row in (self.items or [])
				if self._row_has_link_targets(row)
			]
			if rows_with_links:
				self._remove_allowances_using_links(rows_with_links)

		unlinked_employees = sorted(
			{
				row.employee
				for row in (self.items or [])
				if row.employee and not self._row_has_link_targets(row)
			}
		)
		if unlinked_employees:
			self._remove_allowances_by_search(unlinked_employees, month, year)

	def _remove_allowances_by_reference(self) -> bool:
		target_rows = frappe.get_all(
			"VNT Salary Slip Item",
			filters={"recurring_extra_benefit": self.name},
			fields=["name", "parent"],
			limit_page_length=0,
		)
		if not target_rows:
			return False

		rows_by_slip: Dict[str, List[str]] = {}
		for row in target_rows:
			parent = row.get("parent")
			item_name = row.get("name")
			if not parent or not item_name:
				continue
			rows_by_slip.setdefault(parent, []).append(item_name)

		if not rows_by_slip:
			return False

		for slip_name, item_names in rows_by_slip.items():
			try:
				slip_doc = frappe.get_doc("VNT Salary Slip", slip_name)
			except frappe.DoesNotExistError:
				continue

			slip_doc.flags.ignore_permissions = True
			slip_doc.flags.ignore_validate_update_after_submit = True

			target_names = set(item_names)
			original_items = slip_doc.items or []
			filtered_items = [child for child in original_items if child.name not in target_names]

			if len(filtered_items) == len(original_items):
				continue

			slip_doc.set("items", filtered_items)
			slip_doc.save(ignore_permissions=True)

		return True

	def _remove_allowances_using_links(self, rows: List[Document]):
		if not rows:
			return

		rows_by_slip: Dict[str, List[Document]] = {}
		for row in rows:
			slip_name, item_name = self._row_link_values(row)
			if not slip_name or not item_name:
				continue
			rows_by_slip.setdefault(slip_name, []).append(row)

		for slip_name, linked_rows in rows_by_slip.items():
			slip_doc = frappe.get_doc("VNT Salary Slip", slip_name)
			slip_doc.flags.ignore_permissions = True
			slip_doc.flags.ignore_validate_update_after_submit = True

			target_names = {
				row.get("salary_slip_item")
				for row in linked_rows
				if row.get("salary_slip_item")
			}
			if not target_names:
				continue

			original_items = slip_doc.items or []
			filtered_items = [child for child in original_items if child.name not in target_names]

			if len(filtered_items) == len(original_items):
				continue

			slip_doc.set("items", filtered_items)
			slip_doc.save(ignore_permissions=True)

			for row in linked_rows:
				self._clear_parent_item_links(row)

	def _remove_allowances_by_search(self, employees: List[str], month: str, year: int):
		if not employees:
			return

		slip_map = self._fetch_salary_slips(employees, month, year)
		if not slip_map:
			return

		processed = set()
		for slip_name in slip_map.values():
			if not slip_name or slip_name in processed:
				continue
			processed.add(slip_name)
			slip_doc = frappe.get_doc("VNT Salary Slip", slip_name)
			slip_doc.flags.ignore_permissions = True
			slip_doc.flags.ignore_validate_update_after_submit = True

			original_items = slip_doc.items or []
			filtered_items = [
				child
				for child in original_items
				if getattr(child, "recurring_extra_benefit", None) != self.name
			]

			if len(filtered_items) == len(original_items):
				continue

			slip_doc.set("items", filtered_items)
			slip_doc.save(ignore_permissions=True)

	def _build_salary_slip_child_row(self, row) -> Dict:
		return {
			"allowance_type": row.allowance_type or self.type,
			"he_so": flt(row.he_so),
			"amount": flt(row.amount),
			"so_thang": cint(row.so_thang),
			"tong": flt(row.tong),
			"thue_tncn": flt(row.thue_tncn),
			"thuc_linh": flt(row.thuc_linh),
			"recurring_extra_benefit": self.name,
		}

	def _update_parent_item_links(self, row, slip_name: str, slip_item_name: str):
		if not (row and slip_name and slip_item_name and self._link_fields_available()):
			return
		frappe.db.set_value(
			row.doctype,
			row.name,
			{
				"salary_slip": slip_name,
				"salary_slip_item": slip_item_name,
			},
			update_modified=False,
		)
		row.set("salary_slip", slip_name)
		row.set("salary_slip_item", slip_item_name)

	def _clear_parent_item_links(self, row):
		if not (row and self._link_fields_available()):
			return
		if not (row.get("salary_slip") or row.get("salary_slip_item")):
			return
		frappe.db.set_value(
			row.doctype,
			row.name,
			{
				"salary_slip": None,
				"salary_slip_item": None,
			},
			update_modified=False,
		)
		row.set("salary_slip", None)
		row.set("salary_slip_item", None)

	def _row_has_link_targets(self, row) -> bool:
		if not (row and self._link_fields_available()):
			return False
		slip_name, item_name = self._row_link_values(row)
		return bool(slip_name and item_name)

	def _row_link_values(self, row):
		if not (row and self._link_fields_available()):
			return (None, None)
		return row.get("salary_slip"), row.get("salary_slip_item")

	def _link_fields_available(self) -> bool:
		if self._link_fields_present is not None:
			return self._link_fields_present

		meta = frappe.get_meta("VNT Recurring Extra Benefit Item")
		self._link_fields_present = bool(
			meta.get_field("salary_slip") and meta.get_field("salary_slip_item")
		)
		return self._link_fields_present


def _get_employees_with_allowance(allowance_type: str) -> List[Dict]:
	"""Fetch active employees and allowance values for the given allowance type."""
	allowance_rows = frappe.db.get_all(
		"VNT Employee Allowance Type",
		filters={
			"type": allowance_type,
			"parenttype": "Employee",
			"parentfield": "custom_phu_cap",
		},
		fields=[
			"parent as employee",
			"type",
			"he_so",
			"so_tien_phu_cap",
			"from_date",
			"to_date",
			"creation",
		],
		order_by="from_date desc, creation desc",
		limit_page_length=0,
	)

	if not allowance_rows:
		return []

	latest_allowance = {}
	for row in allowance_rows:
		employee_code = row.get("employee")
		if not employee_code or employee_code in latest_allowance:
			continue
		latest_allowance[employee_code] = row

	if not latest_allowance:
		return []

	employee_codes = list(latest_allowance.keys())
	employees = frappe.get_all(
		"Employee",
		filters={"name": ("in", employee_codes), "status": "Active"},
		fields=["name", "employee_name", "designation"],
		limit_page_length=0,
	)

	result = []
	for emp in employees:
		allowance = latest_allowance.get(emp.name)
		if not allowance:
			continue
		result.append(
			{
				"employee": emp.name,
				"employee_name": emp.employee_name,
				"designation": emp.designation,
				"allowance_type": allowance.get("type"),
				"he_so": allowance.get("he_so"),
				"amount": allowance.get("so_tien_phu_cap"),
				"from_date": allowance.get("from_date"),
				"to_date": allowance.get("to_date"),
			}
		)

	result.sort(key=lambda d: (d.get("employee_name") or d.get("employee") or ""))
	return result
