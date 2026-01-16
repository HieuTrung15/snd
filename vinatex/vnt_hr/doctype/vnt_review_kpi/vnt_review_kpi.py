# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, get_last_day, getdate, nowdate


class VNTReviewKPI(Document):
	pass


@frappe.whitelist()
def get_review_tasks(employee: str, chuky: str, chi_tiet_ky_review: int | str, review_date: str | None = None):
	if not employee:
		frappe.throw(_("Vui lòng chọn Người tạo."))
	if not chuky:
		frappe.throw(_("Vui lòng chọn Kỳ review."))
	if not chi_tiet_ky_review:
		frappe.throw(_("Vui lòng nhập Chi tiết kỳ review."))

	start_date, end_date = _get_review_range(chuky, chi_tiet_ky_review, review_date)

	tasks = frappe.get_all(
		"VNT Task",
		filters={
			"employee": employee,
			"docstatus": ("in", [0, 1]),
		},
		fields=["name", "exp_start_date", "exp_end_date"],
		order_by="exp_start_date asc, exp_end_date asc, modified desc",
	)

	items = []
	for task in tasks:
		task_start, task_end = _normalize_task_dates(task.exp_start_date, task.exp_end_date)
		if not task_start or not task_end:
			continue
		if task_start <= end_date and task_end >= start_date:
			items.append({"congviec": task.name})

	return {
		"items": items,
		"start_date": start_date,
		"end_date": end_date,
	}


def _get_review_range(chuky: str, chi_tiet_ky_review: int | str, review_date: str | None):
	cycle = (chuky or "").strip()
	detail = cint(chi_tiet_ky_review)
	ref_date = getdate(review_date) if review_date else getdate(nowdate())

	if cycle == "Tháng":
		if detail < 1 or detail > 12:
			frappe.throw(_("Tháng không hợp lệ: {0}").format(chi_tiet_ky_review))
		start = date(ref_date.year, detail, 1)
		end = get_last_day(start)
		return start, end

	if cycle == "Quý":
		if detail < 1 or detail > 4:
			frappe.throw(_("Quý không hợp lệ: {0}").format(chi_tiet_ky_review))
		start_month = (detail - 1) * 3 + 1
		start = date(ref_date.year, start_month, 1)
		end = get_last_day(add_months(start, 2))
		return start, end

	if cycle == "Năm":
		if detail <= 0:
			frappe.throw(_("Năm không hợp lệ: {0}").format(chi_tiet_ky_review))
		start = date(detail, 1, 1)
		end = date(detail, 12, 31)
		return start, end

	frappe.throw(_("Kỳ review không hợp lệ: {0}").format(chuky))


def _normalize_task_dates(exp_start_date, exp_end_date):
	start = getdate(exp_start_date) if exp_start_date else None
	end = getdate(exp_end_date) if exp_end_date else None
	if start and end and start > end:
		start, end = end, start
	elif start and not end:
		end = start
	elif end and not start:
		start = end
	return start, end
