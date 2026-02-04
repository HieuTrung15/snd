# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class VNTKPINam(Document):
	def validate(self):
		self._apply_adjustment_policy()

	def _apply_adjustment_policy(self):
		if self.type != "Điều chỉnh":
			self.reference_kpi_nam = None
			self.effective_type = self.type
			return

		if not self.reference_kpi_nam:
			frappe.throw(_("Phiếu KPI Năm điều chỉnh phải chọn phiếu tham chiếu."))

		source = frappe.get_doc("VNT KPI Nam", self.reference_kpi_nam)
		if source.docstatus != 1:
			frappe.throw(_("Phiếu tham chiếu phải ở trạng thái Đã submit."))
		if source.type == "Điều chỉnh":
			frappe.throw(_("Không cho phép điều chỉnh từ một phiếu Điều chỉnh khác."))

		if self.kpi_year and source.kpi_year and cint(self.kpi_year) != cint(source.kpi_year):
			frappe.throw(_("KPI năm của phiếu điều chỉnh phải giống phiếu tham chiếu."))
		if self.department and source.department and self.department != source.department:
			frappe.throw(_("Phòng/Ban của phiếu điều chỉnh phải giống phiếu tham chiếu."))

		self.kpi_year = source.kpi_year
		self.department = source.department
		self.effective_type = source.effective_type or source.type


@frappe.whitelist()
def get_effective_kpi_nam_items(kpi_year: int | str, department: str, business_type: str):
	if not kpi_year:
		frappe.throw(_("Thiếu năm KPI."))
	if not department:
		frappe.throw(_("Thiếu Phòng/Ban."))
	if not business_type or business_type == "Điều chỉnh":
		frappe.throw(_("Phân loại không hợp lệ để lấy KPI hiệu lực."))

	base_rows = frappe.get_all(
		"VNT KPI Nam",
		filters={
			"kpi_year": cint(kpi_year),
			"department": department,
			"docstatus": 1,
			"type": business_type,
		},
		fields=["name", "kpi_name"],
		order_by="modified desc",
		limit_page_length=500,
	)

	items = []
	for base in base_rows:
		effective_name = _get_latest_adjustment("VNT KPI Nam", "reference_kpi_nam", base.name) or base.name
		effective_data = frappe.db.get_value(
			"VNT KPI Nam",
			effective_name,
			["name", "kpi_name"],
			as_dict=True,
		)
		if not effective_data:
			continue
		items.append(
			{
				"name": effective_data.name,
				"kpi_name": effective_data.kpi_name,
				"source_name": base.name,
			}
		)

	return {"items": items}


def _get_latest_adjustment(doctype: str, reference_field: str, source_name: str):
	row = frappe.get_all(
		doctype,
		filters={
			reference_field: source_name,
			"docstatus": 1,
			"type": "Điều chỉnh",
		},
		fields=["name"],
		order_by="modified desc",
		limit_page_length=1,
	)
	return row[0].name if row else None
