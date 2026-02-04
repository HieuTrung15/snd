# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


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

	total_payload_percent = 0.0
	item_deadline = getdate(item.date) if item.date else None
	default_type = doc.type
	for idx, entry in enumerate(parsed_entries, start=1):
		_validate_task_entry(entry, idx, item_deadline, default_type)
		total_payload_percent += flt(entry.get("percent"))

	remaining_existing_percent = sum(
		flt(task.percent) for task in existing_tasks if task.name not in payload_names
	)
	total_after_save = total_payload_percent + remaining_existing_percent
	if total_after_save > allocation_cap_percent + 0.0001:
		frappe.throw(
			_("Vượt quá % phân bổ task: tổng sau lưu {0}%, giới hạn {1}%.").format(
				round(total_after_save, 2), allocation_cap_percent
			)
		)

	created_tasks = []
	updated_tasks = []
	for entry in parsed_entries:
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
		task.deadline = entry.get("deadline")
		task.exp_start_date = entry.get("exp_start_date")
		task.exp_end_date = entry.get("exp_end_date")
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

	remaining_percent = max(allocation_cap_percent - total_after_save, 0)

	return {
		"created_tasks": created_tasks,
		"updated_tasks": updated_tasks,
		"total_after_save": round(total_after_save, 2),
		"remaining_percent": round(remaining_percent, 2),
		"allocation_cap_percent": allocation_cap_percent,
		"kpi_item_percent": flt(item.percent),
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

	allocation_cap_percent = 100.0
	tasks = _get_candidate_tasks(
		employee=doc.emp_chuyenvien,
		department=doc.department,
		kpi_cv_item_name=item.name,
		legacy_item_key=item.cv_chi_tiet,
		minimal=False,
	)

	allocated_percent = round(sum(flt(task.percent) for task in tasks), 2)
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
		"items": items,
	}


def _get_candidate_tasks(
	employee: str,
	department: str,
	kpi_cv_item_name: str,
	legacy_item_key: str | None = None,
	minimal: bool = False,
):
	fields = (
		["name", "percent", "docstatus"]
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
			and (
				ifnull(kpi_cv_item, '') = %(kpi_cv_item)s
				or (%(legacy_value)s != '' and ifnull(`kpi_chuyên_viên`, '') = %(legacy_value)s)
			)
		order by creation asc
		""",
		{
			"kpi_cv_item": kpi_cv_item_name,
			"legacy_value": legacy_value,
		},
		as_dict=True,
	)
	if linked_tasks:
		return linked_tasks

	# Fallback để gom task cũ chưa gắn link KPI item.
	return frappe.db.sql(
		f"""
		select {", ".join(fields)}
		from `tabVNT Task`
		where docstatus in (0, 1)
			and ifnull(kpi_cv_item, '') = ''
			and employee = %(employee)s
			and department = %(department)s
		order by modified desc
		limit 100
		""",
		{
			"employee": employee,
			"department": department,
		},
		as_dict=True,
	)


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

	deadline_date = getdate(deadline)
	if item_deadline and deadline_date > item_deadline:
		frappe.throw(
			_("Dòng {0}: deadline task không được muộn hơn KPI chuyên viên ({1}).").format(
				idx, item_deadline
			)
		)

	start_date = getdate(entry.get("exp_start_date")) if entry.get("exp_start_date") else None
	end_date = getdate(entry.get("exp_end_date")) if entry.get("exp_end_date") else None

	if start_date and end_date and start_date > end_date:
		frappe.throw(_("Dòng {0}: ngày bắt đầu dự kiến không thể lớn hơn ngày kết thúc.").format(idx))

	if item_deadline and end_date and end_date > item_deadline:
		frappe.throw(
			_("Dòng {0}: ngày kết thúc dự kiến không được muộn hơn KPI chuyên viên ({1}).").format(
				idx, item_deadline
			)
		)
