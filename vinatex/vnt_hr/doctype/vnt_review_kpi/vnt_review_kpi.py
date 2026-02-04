# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import date

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, cint, flt, get_last_day, getdate, nowdate


class VNTReviewKPI(Document):
	def validate(self):
		self._sync_items_from_tasks()

	def on_submit(self):
		_rollup_kpi_ban_items(_extract_kpi_ban_items(self))

	def on_cancel(self):
		_rollup_kpi_ban_items(_extract_kpi_ban_items(self))

	def _sync_items_from_tasks(self):
		task_names = [row.congviec for row in (self.items or []) if row.congviec]
		if not task_names:
			return

		task_rows = frappe.get_all(
			"VNT Task",
			filters={"name": ("in", task_names)},
			fields=["name", "progress", "percent", "kpi_cv_item"],
		)
		task_map = {task.name: task for task in task_rows}

		kpi_cv_names = [task.kpi_cv_item for task in task_rows if task.kpi_cv_item]
		kpi_cv_meta_map = _get_kpi_cv_meta_map(kpi_cv_names)

		for row in self.items or []:
			task = task_map.get(row.congviec)
			if not task:
				continue

			percent_cv = flt(task.progress)
			row.percent_cv = percent_cv

			if task.kpi_cv_item:
				row.kpi_cv_item = task.kpi_cv_item
				row.kpi_ban_item = (kpi_cv_meta_map.get(task.kpi_cv_item) or {}).get("kpi_ban_item")


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
		fields=["name", "exp_start_date", "exp_end_date", "deadline", "progress", "percent", "kpi_cv_item"],
		order_by="exp_start_date asc, exp_end_date asc, modified desc",
	)

	kpi_cv_names = [task.kpi_cv_item for task in tasks if task.kpi_cv_item]
	kpi_cv_meta_map = _get_kpi_cv_meta_map(kpi_cv_names)

	items = []
	for task in tasks:
		task_start, task_end = _normalize_task_dates(task.exp_start_date, task.exp_end_date, task.deadline)
		if not task_start or not task_end:
			continue
		if task_start <= end_date and task_end >= start_date:
			percent_cv = flt(task.progress)
			items.append(
				{
					"congviec": task.name,
					"kpi_cv_item": task.kpi_cv_item,
					"kpi_ban_item": (kpi_cv_meta_map.get(task.kpi_cv_item) or {}).get("kpi_ban_item"),
					"percent_cv": percent_cv,
				}
			)

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


def _normalize_task_dates(exp_start_date, exp_end_date, deadline=None):
	start = getdate(exp_start_date) if exp_start_date else None
	end = getdate(exp_end_date) if exp_end_date else None
	due = getdate(deadline) if deadline else None
	if start and end and start > end:
		start, end = end, start
	elif start and not end:
		end = start
	elif end and not start:
		start = end
	elif due:
		start = due
		end = due
	return start, end


def _extract_kpi_ban_items(doc: VNTReviewKPI) -> list[str]:
	return sorted({row.kpi_ban_item for row in (doc.items or []) if row.kpi_ban_item})


def _get_kpi_cv_meta_map(kpi_cv_names: list[str]) -> dict[str, dict]:
	if not kpi_cv_names:
		return {}

	rows = frappe.get_all(
		"VNT KPI Chuyen Vien Item",
		filters={"name": ("in", list(set(kpi_cv_names)))},
		fields=["name", "kpi_ban_item", "percent"],
	)
	return {
		row.name: {
			"kpi_ban_item": row.kpi_ban_item,
			"percent": row.percent,
		}
		for row in rows
	}


def _rollup_kpi_ban_items(kpi_ban_items: list[str]):
	if not kpi_ban_items:
		return

	for item_name in kpi_ban_items:
		row = frappe.db.sql(
			"""
			select
				coalesce(avg(coalesce(i.percent_cv, 0)), 0) as percent_cv_rollup,
				coalesce(sum(coalesce(i.diem_cv_danh_gia, 0)), 0) as diem_cv_rollup,
				coalesce(avg(coalesce(i.percent_ld, 0)), 0) as percent_ld_rollup,
				coalesce(sum(coalesce(i.diem_ld_danh_gia, 0)), 0) as diem_ld_rollup,
				count(i.name) as review_count
			from `tabVNT Review KPI Item` i
			inner join `tabVNT Review KPI` r on r.name = i.parent
			where i.parenttype = 'VNT Review KPI'
				and i.kpi_ban_item = %s
				and r.docstatus = 1
			""",
			(item_name,),
			as_dict=True,
		)[0]

		frappe.db.set_value(
			"VNT KPI Ban Item",
			item_name,
			{
				"percent_cv_rollup": round(flt(row.percent_cv_rollup), 2),
				"diem_cv_rollup": round(flt(row.diem_cv_rollup), 2),
				"percent_ld_rollup": round(flt(row.percent_ld_rollup), 2),
				"diem_ld_rollup": round(flt(row.diem_ld_rollup), 2),
				"review_count": cint(row.review_count),
			},
			update_modified=False,
		)
