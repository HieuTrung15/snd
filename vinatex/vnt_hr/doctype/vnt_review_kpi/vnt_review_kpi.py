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
		# Đồng bộ lại tiến độ/điểm từ task để hạn chế nhập tay sai lệch.
		self._sync_items_from_tasks()
		self._validate_scores()

	def before_submit(self):
		self._validate_unique_monthly_submission()

	def on_submit(self):
		_rollup_kpi_ban_items(_extract_kpi_ban_items(self))
		_rollup_kpi_cv_items(_extract_kpi_cv_items(self))

	def on_cancel(self):
		_rollup_kpi_ban_items(_extract_kpi_ban_items(self))
		_rollup_kpi_cv_items(_extract_kpi_cv_items(self))

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
				meta = kpi_cv_meta_map.get(task.kpi_cv_item) or {}
				row.kpi_ban_item = meta.get("kpi_ban_item")
				kpi_ban_share = meta.get("percent_kpi_ban")
				if kpi_ban_share is None:
					kpi_ban_share = 100
				row.diem_cv_danh_gia = _calc_diem_cv(
					percent_cv=percent_cv,
					task_percent=flt(task.percent),
					kpi_ban_share=flt(kpi_ban_share),
				)

	def _validate_scores(self):
		for row in self.items or []:
			if row.diem_cv_danh_gia is not None and not (0 <= flt(row.diem_cv_danh_gia) <= 10):
				frappe.throw(_("Điểm CV đánh giá phải trong thang 0-10."))
			if row.diem_ld_danh_gia is not None and not (0 <= flt(row.diem_ld_danh_gia) <= 10):
				frappe.throw(_("Điểm LĐ đánh giá phải trong thang 0-10."))

	def _validate_unique_monthly_submission(self):
		if not self.employee:
			frappe.throw(_("Vui lòng chọn Người tạo trước khi submit."))
		if not self.date:
			frappe.throw(_("Vui lòng chọn Ngày tạo trước khi submit."))

		review_date = getdate(self.date)
		month_start = date(review_date.year, review_date.month, 1)
		month_end = get_last_day(month_start)
		month_label = f"{review_date.month:02d}/{review_date.year}"

		existing_submitted = frappe.get_all(
			"VNT Review KPI",
			filters={
				"name": ("!=", self.name),
				"docstatus": 1,
				"employee": self.employee,
				"date": ("between", [month_start, month_end]),
			},
			fields=["name"],
			limit_page_length=1,
		)
		if existing_submitted:
			frappe.throw(
				_("Mỗi nhân sự chỉ được submit 1 phiếu Review KPI trong tháng {0}. Phiếu đã submit: {1}.").format(
					month_label, existing_submitted[0].name
				)
			)

@frappe.whitelist()
def get_review_tasks(employee: str, chuky: str, chi_tiet_ky_review: int | str, review_date: str | None = None):
	if not employee:
		frappe.throw(_("Vui lòng chọn Người tạo."))
	if not chuky:
		frappe.throw(_("Vui lòng chọn Kỳ review."))
	if not chi_tiet_ky_review:
		frappe.throw(_("Vui lòng nhập Chi tiết kỳ review."))

	start_date, end_date = _get_review_range(chuky, chi_tiet_ky_review, review_date)

	# Với cơ chế task theo tháng, kỳ review lấy task theo deadline nằm trong kỳ.
	tasks = frappe.get_all(
		"VNT Task",
		filters={
			"employee": employee,
			"docstatus": ("in", [0, 1]),
			"deadline": ("between", [start_date, end_date]),
		},
		fields=["name", "deadline", "progress", "percent", "kpi_cv_item"],
		order_by="deadline asc, modified desc",
	)

	kpi_cv_names = [task.kpi_cv_item for task in tasks if task.kpi_cv_item]
	kpi_cv_meta_map = _get_kpi_cv_meta_map(kpi_cv_names)

	items = []
	for task in tasks:
		percent_cv = flt(task.progress)
		meta = kpi_cv_meta_map.get(task.kpi_cv_item) or {}
		kpi_ban_share = meta.get("percent_kpi_ban")
		if kpi_ban_share is None:
			kpi_ban_share = 100
		items.append(
			{
				"congviec": task.name,
				"kpi_cv_item": task.kpi_cv_item,
				"kpi_ban_item": meta.get("kpi_ban_item"),
				"percent_cv": percent_cv,
				"diem_cv_danh_gia": _calc_diem_cv(
					percent_cv=percent_cv,
					task_percent=flt(task.percent),
					kpi_ban_share=flt(kpi_ban_share),
				),
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


def _extract_kpi_ban_items(doc: VNTReviewKPI) -> list[str]:
	items = doc.items or []
	kpi_ban_items = {row.kpi_ban_item for row in items if row.kpi_ban_item}
	if kpi_ban_items:
		return sorted(kpi_ban_items)

	# Fallback cho dữ liệu cũ: nếu item review chưa lưu kpi_ban_item
	# thì suy ra từ kpi_cv_item để vẫn rollup được khi submit/cancel.
	kpi_cv_items = [row.kpi_cv_item for row in items if row.kpi_cv_item]
	kpi_cv_meta_map = _get_kpi_cv_meta_map(kpi_cv_items)
	for kpi_cv_item in kpi_cv_items:
		kpi_ban_item = (kpi_cv_meta_map.get(kpi_cv_item) or {}).get("kpi_ban_item")
		if kpi_ban_item:
			kpi_ban_items.add(kpi_ban_item)

	return sorted(kpi_ban_items)


def _extract_kpi_cv_items(doc: VNTReviewKPI) -> list[str]:
	return sorted({row.kpi_cv_item for row in (doc.items or []) if row.kpi_cv_item})


def _get_kpi_cv_meta_map(kpi_cv_names: list[str]) -> dict[str, dict]:
	if not kpi_cv_names:
		return {}

	rows = frappe.get_all(
		"VNT KPI Chuyen Vien Item",
		filters={"name": ("in", list(set(kpi_cv_names)))},
		fields=["name", "kpi_ban_item", "percent", "percent_kpi_ban"],
	)
	return {
		row.name: {
			"kpi_ban_item": row.kpi_ban_item,
			"percent": row.percent,
			"percent_kpi_ban": row.percent_kpi_ban,
		}
		for row in rows
	}


def _calc_diem_cv(percent_cv: float, task_percent: float, kpi_ban_share: float) -> float:
	"""Điểm CV theo thang 10: % hoàn thành * % task * % chia KPI Ban."""
	task_share = min(max(flt(task_percent), 0), 100)
	kpi_share = _normalize_share_percent(kpi_ban_share)
	return round((flt(percent_cv) * task_share * kpi_share) / 100000.0, 2)


def _rollup_kpi_ban_items(kpi_ban_items: list[str]):
	if not kpi_ban_items:
		return

	meta_fields = {d.fieldname for d in frappe.get_meta("VNT KPI Ban Item").fields}

	for item_name in kpi_ban_items:
		# Rollup theo từng KPI chuyên viên để áp trần percent_kpi_ban cho mỗi nhánh giao việc.
		rows = frappe.db.sql(
			"""
			select
				i.kpi_cv_item,
				coalesce(sum(coalesce(i.diem_cv_danh_gia, 0)), 0) as cv_score_sum,
				coalesce(sum(coalesce(i.diem_ld_danh_gia, 0)), 0) as ld_score_sum,
				coalesce(sum(case when i.diem_ld_danh_gia is not null then 1 else 0 end), 0) as ld_score_count,
				count(i.name) as review_count
			from `tabVNT Review KPI Item` i
			inner join `tabVNT Review KPI` r on r.name = i.parent
			where i.parenttype = 'VNT Review KPI'
				and i.kpi_ban_item = %s
				and r.docstatus = 1
			group by i.kpi_cv_item
			""",
			(item_name,),
			as_dict=True,
		)

		kpi_cv_names = [row.kpi_cv_item for row in rows if row.kpi_cv_item]
		kpi_cv_meta_map = _get_kpi_cv_meta_map(kpi_cv_names)

		percent_cv_rollup = 0.0
		percent_ld_rollup = 0.0
		has_ld_score = False
		review_count = 0

		for row in rows:
			meta = kpi_cv_meta_map.get(row.kpi_cv_item) or {}
			share = _normalize_share_percent(meta.get("percent_kpi_ban"))
			cv_contribution = _score_to_percent_with_cap(row.cv_score_sum, share)
			ld_contribution = _score_to_percent_with_cap(row.ld_score_sum, share)

			percent_cv_rollup += cv_contribution
			if cint(row.ld_score_count) > 0:
				has_ld_score = True
				percent_ld_rollup += ld_contribution
			review_count += cint(row.review_count)

		percent_cv_rollup = min(round(percent_cv_rollup, 2), 100.0)
		percent_ld_rollup = min(round(percent_ld_rollup, 2), 100.0)
		diem_cv_rollup = round(percent_cv_rollup / 10.0, 2)
		diem_ld_rollup = round(percent_ld_rollup / 10.0, 2)
		completion_percent = percent_ld_rollup if has_ld_score else percent_cv_rollup

		update_values = {}
		if "percent_cv_rollup" in meta_fields:
			update_values["percent_cv_rollup"] = percent_cv_rollup
		if "diem_cv_rollup" in meta_fields:
			update_values["diem_cv_rollup"] = diem_cv_rollup
		if "percent_ld_rollup" in meta_fields:
			update_values["percent_ld_rollup"] = percent_ld_rollup
		if "diem_ld_rollup" in meta_fields:
			update_values["diem_ld_rollup"] = diem_ld_rollup
		if "review_count" in meta_fields:
			update_values["review_count"] = review_count
		if "completion_percent" in meta_fields:
			# Tiến độ tổng hợp của KPI Ban Item, đã áp trần share ở từng KPI chuyên viên.
			update_values["completion_percent"] = completion_percent

		if update_values:
			frappe.db.set_value(
				"VNT KPI Ban Item",
				item_name,
				update_values,
				update_modified=False,
			)


def _rollup_kpi_cv_items(kpi_cv_items: list[str]):
	if not kpi_cv_items:
		return

	meta_fields = {d.fieldname for d in frappe.get_meta("VNT KPI Chuyen Vien Item").fields}

	for item_name in kpi_cv_items:
		# Cập nhật ngược kết quả review về KPI chuyên viên item theo dữ liệu review đã submit.
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
				and i.kpi_cv_item = %s
				and r.docstatus = 1
			""",
			(item_name,),
			as_dict=True,
		)[0]

		update_values = {}
		if "percent_cv_rollup" in meta_fields:
			update_values["percent_cv_rollup"] = round(flt(row.percent_cv_rollup), 2)
		if "diem_cv_rollup" in meta_fields:
			update_values["diem_cv_rollup"] = round(flt(row.diem_cv_rollup), 2)
		if "percent_ld_rollup" in meta_fields:
			update_values["percent_ld_rollup"] = round(flt(row.percent_ld_rollup), 2)
		if "diem_ld_rollup" in meta_fields:
			update_values["diem_ld_rollup"] = round(flt(row.diem_ld_rollup), 2)
		if "review_count" in meta_fields:
			update_values["review_count"] = cint(row.review_count)

		if "rating" in meta_fields:
			score = flt(row.diem_ld_rollup) if flt(row.diem_ld_rollup) > 0 else flt(row.diem_cv_rollup)
			if cint(row.review_count) > 0 and score > 0:
				update_values["rating"] = str(min(max(int(round(score)), 1), 10))
			else:
				update_values["rating"] = None

		if update_values:
			frappe.db.set_value(
				"VNT KPI Chuyen Vien Item",
				item_name,
				update_values,
				update_modified=False,
			)


def _normalize_share_percent(value) -> float:
	# Nếu chưa khai báo % so với KPI Ban thì mặc định toàn bộ thuộc một nhánh giao việc.
	share = flt(value) if value is not None else 100.0
	if share < 0:
		return 0.0
	return min(share, 100.0)


def _score_to_percent_with_cap(score_sum, share_percent: float) -> float:
	# Điểm review đang ở thang 10, quy đổi về % đóng góp và khóa trần theo share.
	percent_value = max(flt(score_sum) * 10.0, 0.0)
	return min(percent_value, share_percent)
