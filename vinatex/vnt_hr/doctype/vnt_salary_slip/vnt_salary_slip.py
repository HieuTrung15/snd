# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import flt


class VNTSalarySlip(Document):
	def before_save(self):
		self._update_allowance_totals()

	def _update_allowance_totals(self):
		total_allowance = 0.0
		total_tax = 0.0
		total_net = 0.0

		for row in self.items or []:
			row_total = self._get_row_total(row)
			row_tax = self._get_row_tax(row)
			row_net = self._get_row_net(row_total, row_tax, row)

			if row.tong in (None, "") or abs(flt(row.tong) - row_total) > 0.0001:
				row.tong = row_total
			if row.thuc_linh in (None, "") or abs(flt(row.thuc_linh) - row_net) > 0.0001:
				row.thuc_linh = row_net

			total_allowance += row_total
			total_tax += row_tax
			total_net += row_net

		self.tong_phu_cap = total_allowance
		self.tong_thue_tncn_phu_cap = total_tax
		self.tong_thuc_linh_phu_cap = total_net

	@staticmethod
	def _get_row_total(row) -> float:
		if row.tong not in (None, ""):
			return flt(row.tong)
		return flt(row.amount) * flt(row.so_thang)

	@staticmethod
	def _get_row_tax(row) -> float:
		return flt(row.thue_tncn)

	@staticmethod
	def _get_row_net(row_total: float, row_tax: float, row) -> float:
		if row.thuc_linh not in (None, ""):
			return flt(row.thuc_linh)
		return row_total - row_tax
