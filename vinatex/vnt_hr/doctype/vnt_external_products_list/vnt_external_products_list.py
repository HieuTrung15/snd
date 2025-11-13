# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
from frappe.utils import flt


class VNTExternalProductsList(Document):
	"""Danh mục tồn kho sản phẩm đối ngoại."""

	def before_save(self):
		self._ensure_child_item_codes()
		self._sync_inventory_balance()

	def _ensure_child_item_codes(self):
		"""Đảm bảo mỗi dòng chi tiết mang đúng mã sản phẩm cha."""
		target_code = self.name or self.item_code
		item_name = self.item_name
		unit = self.unit
		current_qty = self.qty_current
		for row in self.get("list_items") or []:
			row.item_code = target_code
			if item_name and not getattr(row, "item_name", None):
				row.item_name = item_name
			if unit and not getattr(row, "unit", None):
				row.unit = unit
			if current_qty is not None and not getattr(row, "qty_current", None):
				row.qty_current = current_qty
			if not getattr(row, "type", None):
				row.type = "Nhập"

	def _sync_inventory_balance(self):
		child_items = self.get("list_items") or []

		# Không có phát sinh => lấy tồn đầu kỳ bằng tồn hiện tại
		if not child_items:
			raw_value = self.qty_current if self.qty_current not in (None, "") else self.qty_remain
			default_qty = flt(raw_value)
			self.qty_remain = default_qty
			self.qty_current = default_qty
			return

		balance = flt(self.qty_remain)
		for row in child_items:
			qty = flt(getattr(row, "qty", 0))
			row_type = (getattr(row, "type", "") or "").strip().casefold()

			if row_type in {"xuất", "xuat"}:
				balance -= qty
			elif row_type in {"nhập", "nhap"}:
				balance += qty

		self.qty_current = balance
