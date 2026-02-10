# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections import defaultdict
import json
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, formatdate, getdate


class VNTKPIChuyenVien(Document):
	def validate(self):
		self._validate_item_deadlines()

	def _validate_item_deadlines(self):
		ban_item_cache = {}
		for row in self.items or []:
			if not row.kpi_ban_item:
				continue

			if row.kpi_ban_item not in ban_item_cache:
				ban_item_cache[row.kpi_ban_item] = frappe.db.get_value(
					"VNT KPI Ban Item",
					row.kpi_ban_item,
					["date"],
					as_dict=True,
				)

			ban_item = ban_item_cache.get(row.kpi_ban_item) or {}
			ban_deadline = getdate(ban_item.date) if ban_item.get("date") else None
			row_deadline = getdate(row.date) if row.date else None

			if ban_deadline and row_deadline and row_deadline > ban_deadline:
				frappe.throw(
					_(
						"Dòng {0}: hạn KPI Chuyên viên ({1}) không được muộn hơn KPI Ban ({2})."
					).format(row.idx, row.date, ban_item.date)
				)


@frappe.whitelist()
def create_tasks_from_kpi_chuyen_vien(
	kpi_chuyen_vien: str,
	kpi_cv_item: str,
	entries: str | list[dict] | None = None,
):
	if not kpi_chuyen_vien:
		frappe.throw(_("Thiếu chứng từ KPI Chuyên viên."))
	if not kpi_cv_item:
		frappe.throw(_("Thiếu KPI Chuyên viên Item."))

	doc = frappe.get_doc("VNT KPI Chuyen Vien", kpi_chuyen_vien)
	doc.check_permission("read")
	if doc.docstatus == 2:
		frappe.throw(_("Không thể tạo task từ KPI Chuyên viên đã hủy."))

	item_map = {row.name: row for row in (doc.items or [])}
	item = item_map.get(kpi_cv_item)
	if not item:
		frappe.throw(_("KPI Chuyên viên Item không thuộc chứng từ hiện tại."))
	item_deadline = getdate(item.date) if item.date else None
	if not item_deadline:
		frappe.throw(_("KPI chuyên viên chưa có thời hạn, không thể phân bổ theo tháng."))

	parsed_entries = _parse_entries(entries)
	if not parsed_entries:
		frappe.throw(_("Vui lòng nhập ít nhất 1 task chi tiết."))

	allocation_cap_percent = 100.0
	existing_tasks = _get_candidate_tasks(
		employee=doc.emp_chuyenvien,
		department=doc.department,
		kpi_cv_item_name=item.name,
		legacy_item_key=item.cv_chi_tiet,
		minimal=True,
	)
	existing_task_map = {row.name: row for row in existing_tasks}

	payload_names = {entry.get("task_name") for entry in parsed_entries if entry.get("task_name")}
	invalid_names = [name for name in payload_names if name not in existing_task_map]
	if invalid_names:
		frappe.throw(_("Task không thuộc KPI chuyên viên đã chọn: {0}").format(", ".join(invalid_names)))

	default_type = doc.type
	normalized_entries = []
	affected_month_keys = set()
	for idx, entry in enumerate(parsed_entries, start=1):
		validated_dates = _validate_task_entry(entry, idx, item_deadline, default_type)
		deadline_date, start_date = validated_dates
		month_key = _to_month_key(deadline_date)
		normalized_entries.append(
			{
				"raw": entry,
				"deadline_date": deadline_date,
				"start_date": start_date,
				"month_key": month_key,
			}
		)
		affected_month_keys.add(month_key)

	# Nếu update task cũ và đổi tháng, cần kiểm tra lại cả tháng cũ.
	for task_name in payload_names:
		old_task = existing_task_map.get(task_name)
		if old_task and old_task.deadline:
			affected_month_keys.add(_to_month_key(getdate(old_task.deadline)))

	month_tasks = _get_employee_tasks_for_month_keys(
		employee=doc.emp_chuyenvien,
		month_keys=affected_month_keys,
		minimal=True,
	)
	# Tổng hiện hữu của toàn bộ task theo tháng (không phụ thuộc KPI item).
	existing_month_totals = _sum_month_totals(month_tasks)
	base_month_totals = defaultdict(float, existing_month_totals)

	# Khi update task cũ: trừ giá trị cũ khỏi tháng cũ trước khi cộng giá trị mới.
	for task_name in payload_names:
		old_task = existing_task_map.get(task_name)
		if not old_task or not old_task.deadline:
			continue
		old_month_key = _to_month_key(old_task.deadline)
		base_month_totals[old_month_key] -= flt(old_task.percent)
		if base_month_totals[old_month_key] < 0:
			base_month_totals[old_month_key] = 0

	# Cộng giá trị mới theo tháng của payload.
	for normalized in normalized_entries:
		base_month_totals[normalized["month_key"]] += flt(normalized["raw"].get("percent"))

	# Mỗi tháng được cap 100%; nếu dữ liệu cũ >100 thì cho phép giữ nguyên hoặc giảm.
	for month_key, total_after_save in base_month_totals.items():
		existing_total = flt(existing_month_totals.get(month_key))
		if total_after_save <= allocation_cap_percent + 0.0001:
			continue
		if existing_total > allocation_cap_percent + 0.0001 and total_after_save <= existing_total + 0.0001:
			continue
		frappe.throw(
			_(
				"Tháng {0}: tổng phân bổ sau lưu {1}%, vượt giới hạn {2}%."
			).format(_format_month_key(month_key), round(total_after_save, 2), allocation_cap_percent)
		)

	created_tasks = []
	updated_tasks = []
	for normalized in normalized_entries:
		entry = normalized["raw"]
		task_name = entry.get("task_name")
		if task_name:
			task_meta = existing_task_map.get(task_name)
			if task_meta and task_meta.docstatus == 1:
				frappe.throw(
					_("Task {0} đã submit, không thể sửa trong màn tạo nhanh.").format(task_name)
				)
			task = frappe.get_doc("VNT Task", task_name)
		else:
			task = frappe.new_doc("VNT Task")
			task.employee = doc.emp_chuyenvien
			task.department = doc.department
			task.kpi_cv_item = kpi_cv_item
			if item.cv_chi_tiet:
				task.set("kpi_chuyên_viên", item.cv_chi_tiet)

		task.congviec = entry.get("congviec")
		task.set("loại", entry.get("loai") or default_type)
		task.percent = flt(entry.get("percent"))
		deadline_date = normalized["deadline_date"]
		start_date = normalized["start_date"]
		task.deadline = deadline_date
		task.exp_start_date = start_date
		task.exp_end_date = deadline_date
		task.expected_time = flt(entry.get("expected_time"))
		task.details = entry.get("details")
		task.kpi_cv_item = kpi_cv_item
		if item.cv_chi_tiet:
			task.set("kpi_chuyên_viên", item.cv_chi_tiet)

		if task_name:
			task.save()
			updated_tasks.append(task.name)
		else:
			task.insert()
			created_tasks.append(task.name)

	default_month_key = _to_month_key(item_deadline)
	default_allocated = flt(base_month_totals.get(default_month_key))
	month_summaries = _build_month_summaries(base_month_totals, allocation_cap_percent)

	return {
		"created_tasks": created_tasks,
		"updated_tasks": updated_tasks,
		"total_after_save": round(default_allocated, 2),
		"remaining_percent": round(max(allocation_cap_percent - default_allocated, 0), 2),
		"allocated_percent": round(default_allocated, 2),
		"allocation_cap_percent": allocation_cap_percent,
		"kpi_item_percent": flt(item.percent),
		"month_label": _format_month_label(item_deadline),
		"month_summaries": month_summaries,
	}


@frappe.whitelist()
def get_tasks_for_kpi_chuyen_vien_item(kpi_chuyen_vien: str, kpi_cv_item: str):
	if not kpi_chuyen_vien:
		frappe.throw(_("Thiếu chứng từ KPI Chuyên viên."))
	if not kpi_cv_item:
		frappe.throw(_("Thiếu KPI Chuyên viên Item."))

	doc = frappe.get_doc("VNT KPI Chuyen Vien", kpi_chuyen_vien)
	doc.check_permission("read")

	item_map = {row.name: row for row in (doc.items or [])}
	item = item_map.get(kpi_cv_item)
	if not item:
		frappe.throw(_("KPI Chuyên viên Item không thuộc chứng từ hiện tại."))
	item_deadline = getdate(item.date) if item.date else None
	if not item_deadline:
		frappe.throw(_("KPI chuyên viên chưa có thời hạn, không thể phân bổ theo tháng."))

	allocation_cap_percent = 100.0
	tasks = _get_candidate_tasks(
		employee=doc.emp_chuyenvien,
		department=doc.department,
		kpi_cv_item_name=item.name,
		legacy_item_key=item.cv_chi_tiet,
		minimal=False,
	)

	# Summary lấy theo toàn bộ task của nhân sự ở các tháng đang có task của KPI item.
	month_keys = {_to_month_key(item_deadline)}
	for task in tasks:
		if task.get("deadline"):
			month_keys.add(_to_month_key(task.deadline))

	month_tasks = _get_employee_tasks_for_month_keys(
		employee=doc.emp_chuyenvien,
		month_keys=month_keys,
		minimal=True,
	)
	month_totals = _sum_month_totals(month_tasks)
	default_month_key = _to_month_key(item_deadline)
	allocated_percent = round(flt(month_totals.get(default_month_key)), 2)
	remaining_percent = max(allocation_cap_percent - allocated_percent, 0)

	items = []
	for task in tasks:
		items.append(
			{
				"task_name": task.name,
				"congviec": task.congviec,
				"loai": task.loai,
				"percent": task.percent,
				"deadline": task.deadline,
				"exp_start_date": task.exp_start_date,
				"exp_end_date": task.exp_end_date,
				"expected_time": task.expected_time,
				"details": task.details,
			}
		)

	return {
		"item_percent": flt(item.percent),
		"allocated_percent": allocated_percent,
		"remaining_percent": round(remaining_percent, 2),
		"default_type": doc.type,
		"allocation_cap_percent": allocation_cap_percent,
		"month_label": _format_month_label(item_deadline),
		"month_summaries": _build_month_summaries(month_totals, allocation_cap_percent),
		"items": items,
	}


def _get_candidate_tasks(
	employee: str,
	department: str,
	kpi_cv_item_name: str,
	legacy_item_key: str | None = None,
	year: int | None = None,
	month: int | None = None,
	minimal: bool = False,
):
	fields = (
		["name", "percent", "docstatus", "deadline"]
		if minimal
		else [
			"name",
			"congviec",
			"`loại` as loai",
			"percent",
			"deadline",
			"exp_start_date",
			"exp_end_date",
			"expected_time",
			"details",
		]
	)

	legacy_value = legacy_item_key or ""
	linked_tasks = frappe.db.sql(
		f"""
		select {", ".join(fields)}
			from `tabVNT Task`
			where docstatus in (0, 1)
				and (%(year)s is null or year(deadline) = %(year)s)
				and (%(month)s is null or month(deadline) = %(month)s)
				and (
					ifnull(kpi_cv_item, '') = %(kpi_cv_item)s
					or (%(legacy_value)s != '' and ifnull(`kpi_chuyên_viên`, '') = %(legacy_value)s)
				)
		order by creation asc
		""",
			{
				"kpi_cv_item": kpi_cv_item_name,
				"legacy_value": legacy_value,
				"year": year,
				"month": month,
			},
			as_dict=True,
		)
	if linked_tasks:
		return linked_tasks

	# Chỉ fallback khi có filter tháng để hỗ trợ dữ liệu cũ theo cơ chế cũ.
	# Nếu không giới hạn tháng, fallback có thể kéo nhầm task không liên quan KPI item.
	if year is None or month is None:
		return []

	# Fallback để gom task cũ chưa gắn link KPI item.
	return frappe.db.sql(
		f"""
		select {", ".join(fields)}
			from `tabVNT Task`
			where docstatus in (0, 1)
				and (%(year)s is null or year(deadline) = %(year)s)
				and (%(month)s is null or month(deadline) = %(month)s)
				and ifnull(kpi_cv_item, '') = ''
				and employee = %(employee)s
				and department = %(department)s
		order by modified desc
		limit 100
		""",
			{
				"employee": employee,
				"department": department,
				"year": year,
				"month": month,
			},
		as_dict=True,
	)


def _get_employee_tasks_for_month_keys(
	employee: str,
	month_keys: set[str],
	minimal: bool = True,
):
	if not employee or not month_keys:
		return []

	fields = ["name", "percent", "docstatus", "deadline"] if minimal else ["name", "percent", "docstatus", "deadline"]
	return frappe.db.sql(
		f"""
			select {", ".join(fields)}
			from `tabVNT Task`
			where docstatus in (0, 1)
				and employee = %(employee)s
				and date_format(deadline, '%%Y-%%m') in %(month_keys)s
		""",
		{
			"employee": employee,
			"month_keys": tuple(sorted(month_keys)),
		},
		as_dict=True,
	)


def _format_month_label(target_date) -> str:
	if not target_date:
		return ""
	return f"{target_date.month:02d}/{target_date.year}"


def _format_month_key(month_key: str) -> str:
	if not month_key or "-" not in month_key:
		return month_key or ""
	year, month = month_key.split("-", 1)
	return f"{month}/{year}"


def _to_month_key(target_date) -> str:
	target_date = getdate(target_date)
	return f"{target_date.year:04d}-{target_date.month:02d}"


def _sum_month_totals(tasks: list[dict]) -> dict[str, float]:
	totals = defaultdict(float)
	for task in tasks or []:
		if not task.get("deadline"):
			continue
		month_key = _to_month_key(task.deadline)
		totals[month_key] += flt(task.percent)
	return totals


def _build_month_summaries(month_totals: dict[str, float], allocation_cap_percent: float) -> list[dict]:
	summaries = []
	for month_key in sorted((month_totals or {}).keys()):
		allocated_percent = round(flt(month_totals.get(month_key)), 2)
		summaries.append(
			{
				"month_key": month_key,
				"month_label": _format_month_key(month_key),
				"allocated_percent": allocated_percent,
				"allocation_cap_percent": allocation_cap_percent,
				"remaining_percent": round(max(allocation_cap_percent - allocated_percent, 0), 2),
			}
		)
	return summaries


def _parse_entries(entries: str | list[dict] | None) -> list[dict]:
	if not entries:
		return []

	if isinstance(entries, str):
		try:
			entries = json.loads(entries)
		except Exception:
			entries = frappe.parse_json(entries)

	if not isinstance(entries, list):
		frappe.throw(_("Dữ liệu task chi tiết không hợp lệ."))

	return [row for row in entries if row and row.get("congviec")]


def _validate_task_entry(entry: dict, idx: int, item_deadline, default_type: str):
	percent = flt(entry.get("percent"))
	if percent <= 0:
		frappe.throw(_("Dòng {0}: % công việc phải lớn hơn 0.").format(idx))

	task_type = entry.get("loai") or default_type
	allowed_map = {
		"Theo kế hoạch": {"Theo kế hoạch", "Nội bộ"},
		"Điều chỉnh": {"Điều chỉnh", "Nội bộ"},
		"Phát sinh": {"Phát sinh", "Nội bộ"},
	}
	allowed_types = allowed_map.get(default_type, {"Theo kế hoạch", "Điều chỉnh", "Phát sinh", "Nội bộ"})
	if task_type not in allowed_types:
		frappe.throw(
			_("Dòng {0}: loại công việc '{1}' không hợp lệ với KPI chuyên viên loại '{2}'.").format(
				idx, task_type, default_type
			)
		)

	deadline = entry.get("deadline")
	if not deadline:
		frappe.throw(_("Dòng {0}: chưa nhập thời hạn hoàn thành.").format(idx))

	deadline_date = _parse_date_input(deadline)
	if item_deadline and deadline_date > item_deadline:
		frappe.throw(
			_("Dòng {0}: thời hạn task ({1}) không được muộn hơn hạn KPI chuyên viên ({2}).").format(
				idx, formatdate(deadline_date), formatdate(item_deadline)
			)
		)
	start_date = _parse_date_input(entry.get("exp_start_date")) if entry.get("exp_start_date") else None

	if not start_date:
		frappe.throw(_("Dòng {0}: cần nhập ngày bắt đầu.").format(idx))

	if start_date and start_date > deadline_date:
		frappe.throw(_("Dòng {0}: ngày bắt đầu dự kiến không thể lớn hơn ngày kết thúc.").format(idx))

	if start_date and (start_date.year != deadline_date.year or start_date.month != deadline_date.month):
		frappe.throw(
			_("Dòng {0}: ngày bắt đầu và thời hạn phải nằm trong cùng một tháng.").format(idx)
		)

	return deadline_date, start_date


def _parse_date_input(value):
	"""Parse date from dialog payload, accepting both system and user date format."""
	if not value:
		return None
	if not isinstance(value, str):
		return getdate(value)

	date_str = value.strip()
	if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
		return getdate(date_str)

	user_date_format = (frappe.db.get_default("date_format") or "").lower()
	parse_day_first = user_date_format.startswith("dd")
	return getdate(date_str, parse_day_first=parse_day_first)
