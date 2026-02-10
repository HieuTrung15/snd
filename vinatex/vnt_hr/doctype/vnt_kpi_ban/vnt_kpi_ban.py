# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class VNTKPIBan(Document):
	def validate(self):
		self._apply_adjustment_policy()

	def _apply_adjustment_policy(self):
		# Phiếu thường thì chính là phiếu đang có hiệu lực.
		if self.type != "Điều chỉnh":
			self.reference_kpi_ban = None
			self.effective_type = self.type
			return

		if not self.reference_kpi_ban:
			frappe.throw(_("Phiếu KPI Ban điều chỉnh phải chọn phiếu tham chiếu."))

		source = frappe.get_doc("VNT KPI Ban", self.reference_kpi_ban)
		if source.docstatus != 1:
			frappe.throw(_("Phiếu tham chiếu phải ở trạng thái Đã submit."))
		if source.type == "Điều chỉnh":
			frappe.throw(_("Không cho phép điều chỉnh từ một phiếu Điều chỉnh khác."))

		if self.kpi_year and source.kpi_year and cint(self.kpi_year) != cint(source.kpi_year):
			frappe.throw(_("KPI năm của phiếu điều chỉnh phải giống phiếu tham chiếu."))
		if self.department and source.department and self.department != source.department:
			frappe.throw(_("KPI Ban của phiếu điều chỉnh phải giống phiếu tham chiếu."))

		self.kpi_year = source.kpi_year
		self.department = source.department
		self.effective_type = source.effective_type or source.type

		if not self.items:
			# Phiếu điều chỉnh mặc định kế thừa item từ phiếu tham chiếu để người dùng chỉnh sửa tiếp.
			for src in source.items or []:
				row = self.append("items", {})
				row.vnt_kpi_nam = src.vnt_kpi_nam
				row.kpi_details = src.kpi_details
				row.percent = src.percent
				row.date = src.date
				row.note = src.note
				row.rating = src.rating
				row.completion_percent = src.completion_percent
				row.percent_cv_rollup = src.percent_cv_rollup
				row.diem_cv_rollup = src.diem_cv_rollup
				row.percent_ld_rollup = src.percent_ld_rollup
				row.diem_ld_rollup = src.diem_ld_rollup
				row.review_count = src.review_count


@frappe.whitelist()
def get_effective_kpi_ban_doc(kpi_year: int | str, department: str, business_type: str):
	if not kpi_year:
		frappe.throw(_("Thiếu năm KPI."))
	if not department:
		frappe.throw(_("Thiếu Phòng/Ban."))
	if not business_type or business_type == "Điều chỉnh":
		frappe.throw(_("Phân loại không hợp lệ để lấy KPI hiệu lực."))

	base = frappe.get_all(
		"VNT KPI Ban",
		filters={
			"kpi_year": cint(kpi_year),
			"department": department,
			"docstatus": 1,
			"type": business_type,
		},
		fields=["name"],
		order_by="modified desc",
		limit_page_length=1,
	)

	if not base:
		return {}

	base_name = base[0].name
	# KPI Ban hiệu lực = phiếu gốc hoặc bản điều chỉnh submit mới nhất của phiếu gốc.
	effective_name = _get_latest_adjustment(base_name) or base_name
	doc = frappe.get_doc("VNT KPI Ban", effective_name)

	items = []
	for row in doc.items or []:
		items.append(
			{
				"name": row.name,
				"vnt_kpi_nam": row.vnt_kpi_nam,
				"kpi_details": row.kpi_details,
				"percent": row.percent,
				"date": row.date,
				"note": row.note,
			}
		)

	return {
		"name": doc.name,
		"source_name": base_name,
		"items": items,
	}


def _get_latest_adjustment(source_name: str):
	row = frappe.get_all(
		"VNT KPI Ban",
		filters={
			"reference_kpi_ban": source_name,
			"docstatus": 1,
			"type": "Điều chỉnh",
		},
		fields=["name"],
		order_by="modified desc",
		limit_page_length=1,
	)
	return row[0].name if row else None
