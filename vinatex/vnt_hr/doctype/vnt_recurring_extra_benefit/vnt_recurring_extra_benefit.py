# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

import io
import re
import unicodedata
from typing import Dict, List

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_last_day, getdate, today
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


class VNTRecurringExtraBenefit(Document):
	_link_fields_present: bool | None = None

	def validate(self):
		self._set_totals_from_items()

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
		allowance_key = _normalize_allowance_type_key(self.type)
		luong_tt = flt(self.luong_tt)
		if allowance_key in {"PC DAC THU", "PC DT"}:
			if not luong_tt:
				luong_data = get_effective_corporate_minimum_wage(
					target_date=self.date,
					month=self.month,
					year=self.year,
				)
				luong_tt = flt(luong_data.get("corporate_minimum_wage"))
				if luong_tt:
					self.luong_tt = luong_tt

			for row in rows:
				he_so = flt(row.get("he_so"))
				row["amount"] = luong_tt * he_so

		return {"items": rows, "luong_tt": luong_tt}

	@frappe.whitelist()
	def fetch_luong_tt(self):
		"""Fetch corporate minimum wage for current document period."""
		return get_effective_corporate_minimum_wage(
			target_date=self.date,
			month=self.month,
			year=self.year,
		)

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

	def _set_totals_from_items(self):
		total_allowance = 0.0
		total_tax = 0.0
		total_net = 0.0
		for row in self.items or []:
			total_allowance += flt(row.tong)
			total_tax += flt(row.thue_tncn)
			total_net += flt(row.thuc_linh)

		self.tong_pc = total_allowance
		self.tong_thue_tncn = total_tax
		self.tong_thuc_linh = total_net

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
			"thue",
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
				"thue": allowance.get("thue"),
				"from_date": allowance.get("from_date"),
				"to_date": allowance.get("to_date"),
			}
		)

	result.sort(key=lambda d: (d.get("employee_name") or d.get("employee") or ""))
	return result


@frappe.whitelist()
def download_recurring_extra_benefit_excel(docname: str | None = None):
	"""Download Excel for recurring extra benefit document."""
	if not docname:
		frappe.throw(_("Thiếu tham chiếu chứng từ để tải xuống Excel."))

	doc = frappe.get_doc("VNT Recurring Extra Benefit", docname)
	doc.check_permission("read")

	selected_type = (doc.type or "").strip()
	selected_key = _normalize_allowance_type_key(selected_type)
	if selected_key == "PC CDS":
		filecontent, filename = _build_pc_cds_workbook(doc)
	elif selected_key in {"PC BAN CHQS", "PC CHQS"}:
		filecontent, filename = _build_pc_ban_chqs_workbook(doc)
	elif selected_key in {"PC DAC THU", "PC DT"}:
		filecontent, filename = _build_pc_dac_thu_workbook(doc)
	else:
		frappe.throw(
			_('Hiện chỉ hỗ trợ tải Excel cho "Loại phụ cấp" là PC CĐS, PC Ban CHQS hoặc PC đặc thù.')
		)

	frappe.response["filename"] = filename
	frappe.response["filecontent"] = filecontent
	frappe.response["type"] = "binary"


@frappe.whitelist()
def get_effective_corporate_minimum_wage(
	target_date: str | None = None, month: str | None = None, year: int | str | None = None
):
	"""Return corporate minimum wage from submitted and currently effective salary parameter."""
	effective_date = _resolve_salary_parameter_effective_date(
		target_date=target_date, month=month, year=year
	)

	rows = frappe.db.sql(
		"""
		SELECT
			name,
			corporate_minimum_wage
		FROM `tabVNT Salary Parameter`
		WHERE docstatus = 1
		  AND COALESCE(from_date, '1900-01-01') <= %(effective_date)s
		  AND COALESCE(NULLIF(to_date, '0000-00-00'), '2999-12-31') >= %(effective_date)s
		ORDER BY from_date DESC, creation DESC
		LIMIT 1
		""",
		{"effective_date": effective_date},
		as_dict=True,
	)

	if not rows:
		latest = frappe.get_all(
			"VNT Salary Parameter",
			filters={"docstatus": 1},
			fields=["name", "corporate_minimum_wage"],
			order_by="from_date desc, creation desc",
			limit_page_length=1,
		)
		if not latest:
			return {"corporate_minimum_wage": 0, "salary_parameter": None, "effective_date": str(effective_date)}
		row = latest[0]
		return {
			"corporate_minimum_wage": flt(row.corporate_minimum_wage),
			"salary_parameter": row.name,
			"effective_date": str(effective_date),
		}

	row = rows[0]
	return {
		"corporate_minimum_wage": flt(row.corporate_minimum_wage),
		"salary_parameter": row.name,
		"effective_date": str(effective_date),
	}


def _build_pc_cds_workbook(doc: Document):
	"""Build the Excel template for allowance type PC CĐS."""
	workbook = Workbook()
	ws = workbook.active
	ws.title = "PC CDS"
	items = list(doc.get("items") or [])
	employee_info_map = _get_employee_info_map(items)
	preparer_name = _resolve_preparer_name(doc, employee_info_map)

	column_widths = {
		"A": 6,   # TT
		"B": 28,  # Họ và tên
		"C": 30,  # Chức danh
		"D": 18,  # Tiền phụ cấp
		"E": 18,  # Thuế TNCN
		"F": 20,  # Thu nhập thực lĩnh
		"G": 14,  # Ghi chú
	}
	for col, width in column_widths.items():
		ws.column_dimensions[col].width = width

	thin_side = Side(style="thin", color="000000")
	thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

	header_fill = PatternFill("solid", fgColor="DCE6F1")
	total_fill = PatternFill("solid", fgColor="C6EFCE")

	company_title = "TẬP ĐOÀN DỆT MAY VIỆT NAM"
	branch_title = ((doc.branch or "").strip() or "VĂN PHÒNG 1").upper()
	month_label = _resolve_month_label(doc.month)
	year_label = str(cint(doc.year) or "")

	ws.merge_cells("A1:C1")
	ws["A1"] = company_title
	ws["A1"].font = Font(bold=True, size=13)

	ws.merge_cells("A2:C2")
	ws["A2"] = branch_title
	ws["A2"].font = Font(bold=True, size=13)

	ws.merge_cells("A3:G3")
	ws["A3"] = "BẢNG THANH TOÁN PHỤ CẤP CHO NHÂN SỰ BAN QUẢN LÝ CHUYỂN ĐỔI SỐ"
	ws["A3"].alignment = Alignment(horizontal="center", vertical="center")
	ws["A3"].font = Font(bold=True, size=15)

	ws.merge_cells("A4:G4")
	ws["A4"] = f"THÁNG {month_label} NĂM {year_label}"
	ws["A4"].alignment = Alignment(horizontal="center", vertical="center")
	ws["A4"].font = Font(bold=True, size=14)

	ws.merge_cells("A5:G5")
	ws["A5"] = "(Theo Tờ trình ngày 26/06/2023 của Ban QL Dự án chuyển đổi số)"
	ws["A5"].alignment = Alignment(horizontal="center", vertical="center")
	ws["A5"].font = Font(italic=True, bold=True, size=12)

	ws.merge_cells("E6:G6")
	ws["E6"] = "Đơn vị tính: đồng"
	ws["E6"].alignment = Alignment(horizontal="right", vertical="center")
	ws["E6"].font = Font(italic=True, size=11)

	headers = ["TT", "Họ và tên", "Chức danh", "Tiền phụ cấp", "Thuế TNCN", "Thu nhập thực lĩnh", "Ghi chú"]
	header_start_row = 7
	header_end_row = 8

	for idx, label in enumerate(headers, start=1):
		ws.merge_cells(
			start_row=header_start_row,
			start_column=idx,
			end_row=header_end_row,
			end_column=idx,
		)
		cell = ws.cell(row=header_start_row, column=idx)
		cell.value = label
		cell.font = Font(bold=True, size=12)
		cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
		cell.fill = header_fill
		cell.border = thin_border
		ws.cell(row=header_end_row, column=idx).border = thin_border

	ws.row_dimensions[header_start_row].height = 24
	ws.row_dimensions[header_end_row].height = 24

	data_start_row = 9
	amount_fmt = '#,##0;[Red]-#,##0;"-"'
	for row_idx, row in enumerate(items, start=data_start_row):
		emp_info = employee_info_map.get(row.employee) or {}
		ws.cell(row=row_idx, column=1, value=row_idx - data_start_row + 1)
		ws.cell(row=row_idx, column=2, value=emp_info.get("employee_name") or row.employee or "")
		ws.cell(row=row_idx, column=3, value=row.designation or "")
		ws.cell(row=row_idx, column=4, value=flt(row.tong))
		ws.cell(row=row_idx, column=5, value=flt(row.thue_tncn))
		ws.cell(row=row_idx, column=6, value=flt(row.thuc_linh))
		ws.cell(row=row_idx, column=7, value="")

		for col_idx in range(1, 8):
			cell = ws.cell(row=row_idx, column=col_idx)
			cell.border = thin_border
			if col_idx == 1:
				cell.alignment = Alignment(horizontal="center", vertical="center")
			elif col_idx in (2, 7):
				cell.alignment = Alignment(horizontal="left", vertical="center")
			elif col_idx == 3:
				cell.alignment = Alignment(horizontal="center", vertical="center")
			else:
				cell.alignment = Alignment(horizontal="right", vertical="center")
				cell.number_format = amount_fmt

	if items:
		last_data_row = data_start_row + len(items) - 1
	else:
		last_data_row = data_start_row

	total_row = last_data_row + 1
	ws.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=3)
	ws.cell(row=total_row, column=1).value = "Tổng cộng :"

	ws.cell(row=total_row, column=4, value=flt(doc.tong_pc))
	ws.cell(row=total_row, column=5, value=flt(doc.tong_thue_tncn))
	ws.cell(row=total_row, column=6, value=flt(doc.tong_thuc_linh))
	ws.cell(row=total_row, column=7, value="")

	for col_idx in range(1, 8):
		cell = ws.cell(row=total_row, column=col_idx)
		cell.font = Font(bold=True, size=12)
		cell.border = thin_border
		cell.fill = total_fill
		if col_idx == 1:
			cell.alignment = Alignment(horizontal="center", vertical="center")
		elif col_idx in (4, 5, 6):
			cell.alignment = Alignment(horizontal="right", vertical="center")
			cell.number_format = amount_fmt
		else:
			cell.alignment = Alignment(horizontal="left", vertical="center")

	date_row = total_row + 2
	ws.merge_cells(start_row=date_row, start_column=5, end_row=date_row, end_column=7)
	ws.cell(row=date_row, column=5).value = f"Hà Nội, ngày      tháng      năm {year_label}"
	ws.cell(row=date_row, column=5).alignment = Alignment(horizontal="right", vertical="center")
	ws.cell(row=date_row, column=5).font = Font(italic=True, size=12)

	sign_title_row = total_row + 4
	sign_name_row = total_row + 11
	sign_blocks = [
		("TỔNG GIÁM ĐỐC", "Cao Hữu Hiếu", 1, 2),
		("TRƯỞNG BAN TCKT", "Nguyễn Ngọc Cách", 3, 4),
		("TRƯỞNG BAN QLNNL", "Trần Thị Thu Thảo", 5, 6),
		("LẬP BIỂU", preparer_name, 7, 7),
	]

	for title, signer, start_col, end_col in sign_blocks:
		ws.merge_cells(
			start_row=sign_title_row,
			start_column=start_col,
			end_row=sign_title_row,
			end_column=end_col,
		)
		title_cell = ws.cell(row=sign_title_row, column=start_col)
		title_cell.value = title
		title_cell.alignment = Alignment(horizontal="center", vertical="center")
		title_cell.font = Font(bold=True, size=12)

		ws.merge_cells(
			start_row=sign_name_row,
			start_column=start_col,
			end_row=sign_name_row,
			end_column=end_col,
		)
		name_cell = ws.cell(row=sign_name_row, column=start_col)
		name_cell.value = signer
		name_cell.alignment = Alignment(horizontal="center", vertical="center")
		name_cell.font = Font(bold=True, size=12)

	ws.freeze_panes = "A9"
	_append_pc_cds_ds_chi_sheet(
		workbook=workbook,
		doc=doc,
		items=items,
		employee_info_map=employee_info_map,
		month_label=month_label,
		year_label=year_label,
	)

	output = io.BytesIO()
	workbook.save(output)
	output.seek(0)

	filename = f"bang-thanh-toan-pc-cds-{(month_label or 'thang')}-{(year_label or 'nam')}.xlsx"
	return output.getvalue(), filename


def _build_pc_ban_chqs_workbook(doc: Document):
	"""Build the Excel template for allowance type PC Ban CHQS."""
	workbook = Workbook()
	ws = workbook.active
	ws.title = "PC Ban CHQS"

	items = list(doc.get("items") or [])
	employee_info_map = _get_employee_info_map(items)
	preparer_name = _resolve_preparer_name(doc, employee_info_map)
	month_label = _resolve_month_label(doc.month)
	year_label = str(cint(doc.year) or "")

	column_widths = {
		"A": 6,   # TT
		"B": 28,  # Họ và tên
		"C": 26,  # Chức vụ
		"D": 16,  # Phụ cấp 1 tháng
		"E": 10,  # Số tháng
		"F": 16,  # Mức hưởng
		"G": 16,  # Thu nhập thực lĩnh
		"H": 14,  # Ghi chú
	}
	for col, width in column_widths.items():
		ws.column_dimensions[col].width = width

	thin_side = Side(style="thin", color="000000")
	thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
	header_fill = PatternFill("solid", fgColor="E6E6E6")
	total_fill = PatternFill("solid", fgColor="C6EFCE")

	company_title = "TẬP ĐOÀN DỆT MAY VIỆT NAM"
	branch_title = ((doc.branch or "").strip() or "VĂN PHÒNG 1").upper()

	ws.merge_cells("A1:C1")
	ws["A1"] = company_title
	ws["A1"].font = Font(size=13)

	ws.merge_cells("A2:C2")
	ws["A2"] = branch_title
	ws["A2"].font = Font(bold=True, size=13)

	ws.merge_cells("A4:H4")
	ws["A4"] = "BẢNG THANH TOÁN PHỤ CẤP BAN CHỈ HUY QUÂN SỰ"
	ws["A4"].font = Font(bold=True, size=15)
	ws["A4"].alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells("A5:H5")
	ws["A5"] = _build_chqs_period_title(doc.month, year_label)
	ws["A5"].font = Font(bold=True, size=14)
	ws["A5"].alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells("G6:H6")
	ws["G6"] = "Đơn vị tính: đồng"
	ws["G6"].font = Font(italic=True, size=11)
	ws["G6"].alignment = Alignment(horizontal="right", vertical="center")

	headers = [
		"TT",
		"Họ và tên",
		"Chức vụ",
		"Phụ cấp 1 tháng",
		"Số tháng",
		"Mức hưởng",
		"Thu nhập thực lĩnh",
		"Ghi chú",
	]
	header_start_row = 7
	header_end_row = 8

	for idx, label in enumerate(headers, start=1):
		ws.merge_cells(
			start_row=header_start_row,
			start_column=idx,
			end_row=header_end_row,
			end_column=idx,
		)
		cell = ws.cell(row=header_start_row, column=idx)
		cell.value = label
		cell.font = Font(bold=True, size=12)
		cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
		cell.fill = header_fill
		cell.border = thin_border
		ws.cell(row=header_end_row, column=idx).border = thin_border

	ws.row_dimensions[header_start_row].height = 24
	ws.row_dimensions[header_end_row].height = 24

	data_start_row = 9
	amount_fmt = '#,##0;[Red]-#,##0;"-"'
	total_monthly = 0.0
	total_months = 0

	for idx, row in enumerate(items, start=1):
		current_row = data_start_row + idx - 1
		emp_info = employee_info_map.get(row.employee) or {}
		monthly_amount = flt(row.amount)
		months_count = cint(row.so_thang)
		total_monthly += monthly_amount
		total_months += months_count

		row_data = [
			idx,
			emp_info.get("employee_name") or row.employee or "",
			row.designation or "",
			monthly_amount,
			months_count,
			flt(row.tong),
			flt(row.thuc_linh),
			"",
		]

		for col_idx, value in enumerate(row_data, start=1):
			cell = ws.cell(row=current_row, column=col_idx, value=value)
			cell.border = thin_border
			if col_idx == 1:
				cell.alignment = Alignment(horizontal="center", vertical="center")
			elif col_idx in (2, 3, 8):
				cell.alignment = Alignment(horizontal="left", vertical="center")
			elif col_idx == 5:
				cell.alignment = Alignment(horizontal="right", vertical="center")
				cell.number_format = "0"
			else:
				cell.alignment = Alignment(horizontal="right", vertical="center")
				cell.number_format = amount_fmt

	last_data_row = data_start_row + max(len(items), 1) - 1
	total_row = last_data_row + 1

	ws.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=3)
	ws.cell(row=total_row, column=1, value="Tổng cộng :")
	ws.cell(row=total_row, column=4, value=total_monthly)
	ws.cell(row=total_row, column=5, value=total_months)
	ws.cell(row=total_row, column=6, value=flt(doc.tong_pc))
	ws.cell(row=total_row, column=7, value=flt(doc.tong_thuc_linh))
	ws.cell(row=total_row, column=8, value="")

	for col_idx in range(1, 9):
		cell = ws.cell(row=total_row, column=col_idx)
		cell.font = Font(bold=True, size=12)
		cell.border = thin_border
		cell.fill = total_fill
		if col_idx == 1:
			cell.alignment = Alignment(horizontal="right", vertical="center")
		elif col_idx in (4, 6, 7):
			cell.alignment = Alignment(horizontal="right", vertical="center")
			cell.number_format = amount_fmt
		elif col_idx == 5:
			cell.alignment = Alignment(horizontal="right", vertical="center")
			cell.number_format = "0"
		else:
			cell.alignment = Alignment(horizontal="left", vertical="center")

	date_row = total_row + 2
	ws.merge_cells(start_row=date_row, start_column=5, end_row=date_row, end_column=8)
	ws.cell(row=date_row, column=5, value=f"Hà Nội, ngày      tháng      năm {year_label}")
	ws.cell(row=date_row, column=5).alignment = Alignment(horizontal="right", vertical="center")
	ws.cell(row=date_row, column=5).font = Font(italic=True, size=12)

	sign_title_row = total_row + 4
	sign_name_row = total_row + 10
	sign_blocks = [
		("TỔNG GIÁM ĐỐC", "Cao Hữu Hiếu", 1, 2),
		("KẾ TOÁN TRƯỞNG", "Nguyễn Ngọc Cách", 3, 4),
		("TRƯỞNG BAN QLNNL", "Trần Thị Thu Thảo", 5, 6),
		("LẬP BIỂU", preparer_name, 7, 8),
	]

	for title, signer, start_col, end_col in sign_blocks:
		ws.merge_cells(
			start_row=sign_title_row,
			start_column=start_col,
			end_row=sign_title_row,
			end_column=end_col,
		)
		title_cell = ws.cell(row=sign_title_row, column=start_col)
		title_cell.value = title
		title_cell.alignment = Alignment(horizontal="center", vertical="center")
		title_cell.font = Font(bold=True, size=13)

		ws.merge_cells(
			start_row=sign_name_row,
			start_column=start_col,
			end_row=sign_name_row,
			end_column=end_col,
		)
		name_cell = ws.cell(row=sign_name_row, column=start_col)
		name_cell.value = signer
		name_cell.alignment = Alignment(horizontal="center", vertical="center")
		name_cell.font = Font(bold=True, size=12)

	ws.freeze_panes = "A9"
	_append_pc_chqs_ds_chi_sheet(
		workbook=workbook,
		doc=doc,
		items=items,
		employee_info_map=employee_info_map,
		month_label=month_label,
		year_label=year_label,
	)

	output = io.BytesIO()
	workbook.save(output)
	output.seek(0)

	filename = f"bang-thanh-toan-pc-ban-chqs-{(month_label or 'thang')}-{(year_label or 'nam')}.xlsx"
	return output.getvalue(), filename


def _build_pc_dac_thu_workbook(doc: Document):
	"""Build the Excel template for allowance type PC Đặc thù."""
	workbook = Workbook()
	ws = workbook.active
	ws.title = "ĐT"

	items = list(doc.get("items") or [])
	employee_info_map = _get_employee_info_map(items)
	preparer_name = _resolve_preparer_name(doc, employee_info_map)
	year_label = str(cint(doc.year) or "")
	month_tokens = _extract_valid_month_tokens(doc.month)
	first_month = month_tokens[0] if month_tokens else None
	second_month = month_tokens[1] if len(month_tokens) > 1 else None

	column_widths = {
		"A": 4,   # TT
		"B": 24,  # Họ và tên
		"C": 20,  # Chức vụ
		"D": 8,   # Hệ số
		"E": 12,  # Tháng 1
		"F": 12,  # Tháng 2
		"G": 11,  # Tổng
		"H": 10,  # Thuế TNCN
		"I": 12,  # Thu nhập thực lĩnh
		"J": 10,  # Ghi chú
	}
	for col, width in column_widths.items():
		ws.column_dimensions[col].width = width

	thin_side = Side(style="thin", color="000000")
	thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
	header_fill = PatternFill("solid", fgColor="E6E6E6")
	group_fill = PatternFill("solid", fgColor="C6EFCE")
	total_fill = PatternFill("solid", fgColor="C6EFCE")

	company_title = "TẬP ĐOÀN DỆT MAY VIỆT NAM"
	branch_title = ((doc.branch or "").strip() or "VĂN PHÒNG 1").upper()
	month_label_1 = _build_dac_thu_month_header(first_month, year_label)
	month_label_2 = _build_dac_thu_month_header(second_month, year_label)

	ws.merge_cells("A1:C1")
	ws["A1"] = company_title
	ws["A1"].font = Font(size=13)

	ws.merge_cells("A2:C2")
	ws["A2"] = branch_title
	ws["A2"].font = Font(bold=True, size=13)

	ws.merge_cells("A3:J3")
	ws["A3"] = "BẢNG THANH TOÁN PHỤ CẤP TRÁCH NHIỆM NHÓM CÔNG TÁC ĐẶC THÙ"
	ws["A3"].font = Font(bold=True, size=15)
	ws["A3"].alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells("A4:J4")
	ws["A4"] = _build_dac_thu_period_title(doc.month, year_label)
	ws["A4"].font = Font(bold=True, size=14)
	ws["A4"].alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells("I5:J5")
	ws["I5"] = "Đơn vị tính: đồng"
	ws["I5"].font = Font(italic=True, size=11)
	ws["I5"].alignment = Alignment(horizontal="right", vertical="center")

	header_top_row = 6
	header_bottom_row = 7
	for col_idx in (1, 2, 3, 4, 8, 9, 10):
		ws.merge_cells(
			start_row=header_top_row,
			start_column=col_idx,
			end_row=header_bottom_row,
			end_column=col_idx,
		)

	ws.merge_cells(start_row=header_top_row, start_column=5, end_row=header_top_row, end_column=7)

	ws.cell(row=header_top_row, column=1, value="TT")
	ws.cell(row=header_top_row, column=2, value="Họ và tên")
	ws.cell(row=header_top_row, column=3, value="Chức vụ")
	ws.cell(row=header_top_row, column=4, value="Hệ số\nPC đặc\nthù")
	ws.cell(
		row=header_top_row,
		column=5,
		value="Tiền phụ cấp trách nhiệm nhóm công\ntác đặc thù",
	)
	ws.cell(row=header_bottom_row, column=5, value=month_label_1)
	ws.cell(row=header_bottom_row, column=6, value=month_label_2)
	ws.cell(row=header_bottom_row, column=7, value="Tổng")
	ws.cell(row=header_top_row, column=8, value="Thuế TNCN")
	ws.cell(row=header_top_row, column=9, value="Thu nhập\nthực lĩnh")
	ws.cell(row=header_top_row, column=10, value="Ghi chú")

	for row_idx in (header_top_row, header_bottom_row):
		for col_idx in range(1, 11):
			cell = ws.cell(row=row_idx, column=col_idx)
			cell.font = Font(bold=True, size=11)
			cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
			cell.fill = header_fill
			cell.border = thin_border

	ws.cell(row=header_bottom_row, column=5).font = Font(bold=True, size=11, color="FF0000")
	ws.cell(row=header_bottom_row, column=6).font = Font(bold=True, size=11, color="FF0000")
	ws.row_dimensions[header_top_row].height = 26
	ws.row_dimensions[header_bottom_row].height = 26

	group_defs = [
		("HDQT", "I", "Hội đồng quản trị"),
		("CQDH", "II", "Cơ quan điều hành"),
		("BAN", "II", "Chuyên viên các ban"),
	]
	grouped_items = {key: [] for key, _, _ in group_defs}
	for row in items:
		emp_info = employee_info_map.get(row.employee) or {}
		group_key = _categorize_dac_thu_group(emp_info.get("department"))
		grouped_items.setdefault(group_key, []).append(row)

	data_start_row = 9
	current_row = data_start_row
	serial_no = 1
	amount_fmt = '#,##0;[Red]-#,##0;"-"'
	total_he_so = 0.0
	total_month_1 = 0.0
	total_month_2 = 0.0

	for key, roman, label in group_defs:
		ws.cell(row=current_row, column=1, value=roman)
		ws.merge_cells(start_row=current_row, start_column=2, end_row=current_row, end_column=10)
		ws.cell(row=current_row, column=2, value=label)
		for col_idx in range(1, 11):
			cell = ws.cell(row=current_row, column=col_idx)
			cell.fill = group_fill
			cell.border = thin_border
			if col_idx == 1:
				cell.alignment = Alignment(horizontal="center", vertical="center")
				cell.font = Font(bold=True, size=12)
			elif col_idx == 2:
				cell.alignment = Alignment(horizontal="left", vertical="center")
				cell.font = Font(bold=True, size=12)
		current_row += 1

		group_rows = grouped_items.get(key) or []
		if not group_rows:
			for col_idx in range(1, 11):
				cell = ws.cell(row=current_row, column=col_idx, value="")
				cell.border = thin_border
				cell.alignment = Alignment(horizontal="center", vertical="center")
			current_row += 1
			continue

		for row in group_rows:
			emp_info = employee_info_map.get(row.employee) or {}
			monthly_amount = flt(row.amount)
			month_count = max(cint(row.so_thang), 0)
			month_1_amount = monthly_amount if month_count >= 1 else 0.0
			month_2_amount = monthly_amount if month_count >= 2 else 0.0

			total_he_so += flt(row.he_so)
			total_month_1 += month_1_amount
			total_month_2 += month_2_amount

			row_data = [
				serial_no,
				emp_info.get("employee_name") or row.employee or "",
				row.designation or "",
				flt(row.he_so),
				month_1_amount,
				month_2_amount,
				flt(row.tong),
				flt(row.thue_tncn),
				flt(row.thuc_linh),
				"",
			]

			for col_idx, value in enumerate(row_data, start=1):
				cell = ws.cell(row=current_row, column=col_idx, value=value)
				cell.border = thin_border
				if col_idx == 1:
					cell.alignment = Alignment(horizontal="center", vertical="center")
				elif col_idx in (2, 3, 10):
					cell.alignment = Alignment(horizontal="left", vertical="center")
				elif col_idx == 4:
					cell.alignment = Alignment(horizontal="center", vertical="center")
					cell.number_format = "0.00"
				else:
					cell.alignment = Alignment(horizontal="right", vertical="center")
					cell.number_format = amount_fmt

			serial_no += 1
			current_row += 1

	total_row = current_row
	ws.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=2)
	ws.cell(row=total_row, column=1, value="Tổng cộng :")
	ws.cell(row=total_row, column=4, value=total_he_so)
	ws.cell(row=total_row, column=5, value=total_month_1)
	ws.cell(row=total_row, column=6, value=total_month_2)
	ws.cell(row=total_row, column=7, value=flt(doc.tong_pc))
	ws.cell(row=total_row, column=8, value=flt(doc.tong_thue_tncn))
	ws.cell(row=total_row, column=9, value=flt(doc.tong_thuc_linh))
	ws.cell(row=total_row, column=10, value="")

	for col_idx in range(1, 11):
		cell = ws.cell(row=total_row, column=col_idx)
		cell.font = Font(bold=True, size=12)
		cell.border = thin_border
		cell.fill = total_fill
		if col_idx in (4,):
			cell.alignment = Alignment(horizontal="center", vertical="center")
			cell.number_format = "0.00"
		elif col_idx in (5, 6, 7, 8, 9):
			cell.alignment = Alignment(horizontal="right", vertical="center")
			cell.number_format = amount_fmt
		elif col_idx == 1:
			cell.alignment = Alignment(horizontal="center", vertical="center")
		else:
			cell.alignment = Alignment(horizontal="left", vertical="center")

	date_row = total_row + 2
	ws.merge_cells(start_row=date_row, start_column=8, end_row=date_row, end_column=10)
	ws.cell(row=date_row, column=8, value=f"Hà Nội, ngày      tháng      năm {year_label}")
	ws.cell(row=date_row, column=8).alignment = Alignment(horizontal="right", vertical="center")
	ws.cell(row=date_row, column=8).font = Font(italic=True, size=12)

	sign_title_row = total_row + 4
	sign_name_row = total_row + 11
	sign_blocks = [
		("TỔNG GIÁM ĐỐC", "Cao Hữu Hiếu", 1, 2),
		("KẾ TOÁN TRƯỞNG", "Nguyễn Ngọc Cách", 3, 4),
		("TRƯỞNG BAN QLNNL", "Trần Thị Thu Thảo", 5, 7),
		("NGƯỜI LẬP", preparer_name, 8, 10),
	]

	for title, signer, start_col, end_col in sign_blocks:
		ws.merge_cells(
			start_row=sign_title_row,
			start_column=start_col,
			end_row=sign_title_row,
			end_column=end_col,
		)
		title_cell = ws.cell(row=sign_title_row, column=start_col)
		title_cell.value = title
		title_cell.alignment = Alignment(horizontal="center", vertical="center")
		title_cell.font = Font(bold=True, size=12)

		ws.merge_cells(
			start_row=sign_name_row,
			start_column=start_col,
			end_row=sign_name_row,
			end_column=end_col,
		)
		name_cell = ws.cell(row=sign_name_row, column=start_col)
		name_cell.value = signer
		name_cell.alignment = Alignment(horizontal="center", vertical="center")
		name_cell.font = Font(bold=True, size=12)

	ws.freeze_panes = "A9"
	_append_pc_dac_thu_ds_chi_sheet(
		workbook=workbook,
		doc=doc,
		items=items,
		employee_info_map=employee_info_map,
		month_label=_resolve_month_label(doc.month),
		year_label=year_label,
	)

	output = io.BytesIO()
	workbook.save(output)
	output.seek(0)

	filename = f"bang-thanh-toan-pc-dac-thu-{(_resolve_month_label(doc.month) or 'thang')}-{(year_label or 'nam')}.xlsx"
	return output.getvalue(), filename


def _append_pc_dac_thu_ds_chi_sheet(
	workbook: Workbook,
	doc: Document,
	items: List[Document],
	employee_info_map: Dict[str, Dict[str, str]],
	month_label: str,
	year_label: str,
):
	"""Append DS chi sheet for allowance type PC Đặc thù."""
	ws = workbook.create_sheet("DS chi")

	column_widths = {
		"A": 6,
		"B": 24,
		"C": 10,
		"D": 22,
		"E": 16,
		"F": 40,
		"G": 18,
		"H": 14,
		"I": 14,
	}
	for col, width in column_widths.items():
		ws.column_dimensions[col].width = width

	thin_side = Side(style="thin", color="000000")
	thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
	total_fill = PatternFill("solid", fgColor="92D050")
	yellow_fill = PatternFill("solid", fgColor="FFF200")

	company_title = "TẬP ĐOÀN DỆT MAY VIỆT NAM"
	branch_title = ((doc.branch or "").strip() or "VĂN PHÒNG 1").upper()
	year_text = year_label or str(cint(doc.year) or "")
	month_tokens = _extract_valid_month_tokens(doc.month)
	ref_month = f"{month_tokens[0]:02d}" if month_tokens else (month_label.split(",")[0] if month_label else "")

	ws.merge_cells("A1:C1")
	ws["A1"] = company_title
	ws["A1"].font = Font(size=13)

	ws.merge_cells("A2:C2")
	ws["A2"] = branch_title
	ws["A2"].font = Font(bold=True, size=13)
	ws["A2"].alignment = Alignment(horizontal="left", vertical="center")

	ws.merge_cells("B3:F3")
	ws["B3"] = f"BẢNG THANH TOÁN CHI PHỤ CẤP ĐẶC THÙ THÁNG {month_label}/{year_text}"
	ws["B3"].font = Font(bold=True, size=15)
	ws["B3"].alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells("G3:H3")
	ws["G3"] = "Số tham chiếu LTT:"
	ws["G3"].font = Font(bold=True, size=12)
	ws["G3"].alignment = Alignment(horizontal="center", vertical="center")

	ws["I3"] = f"-{ref_month}/{year_text}-"
	ws["I3"].font = Font(bold=True, size=12)
	ws["I3"].alignment = Alignment(horizontal="center", vertical="center")

	headers = [
		"TT",
		"Số tài khoản",
		"Loại tiền",
		"Tên Người hưởng",
		"Số tiền",
		"Nội dung",
		"Chuyển tiền nhanh\n24/7/ Chuyển tiền\nthường ngoài VCB",
		"Tại ngân hàng",
		"Ghi chú",
	]
	header_start_row = 6
	header_end_row = 7

	for idx, label in enumerate(headers, start=1):
		ws.merge_cells(
			start_row=header_start_row,
			start_column=idx,
			end_row=header_end_row,
			end_column=idx,
		)
		cell = ws.cell(row=header_start_row, column=idx)
		cell.value = label
		cell.font = Font(bold=True, size=12)
		cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
		cell.border = thin_border
		ws.cell(row=header_end_row, column=idx).border = thin_border

	ws.row_dimensions[header_start_row].height = 24
	ws.row_dimensions[header_end_row].height = 44

	data_start_row = 8
	content_template = _build_dac_thu_ds_chi_content(doc.month)
	amount_fmt = '#,##0;[Red]-#,##0;"-"'

	for idx, row in enumerate(items, start=1):
		current_row = data_start_row + idx - 1
		emp_info = employee_info_map.get(row.employee) or {}
		bank_name = (emp_info.get("bank_name") or "").strip()
		transfer_mode = "N" if (bank_name and "VCB" not in bank_name.upper()) else ""

		row_data = [
			idx,
			(emp_info.get("bank_ac_no") or "").strip(),
			"VND",
			_to_upper_no_accents(emp_info.get("employee_name") or row.employee or ""),
			flt(row.thuc_linh),
			content_template,
			transfer_mode,
			bank_name,
			"",
		]

		for col_idx, value in enumerate(row_data, start=1):
			cell = ws.cell(row=current_row, column=col_idx, value=value)
			cell.border = thin_border
			if col_idx in (1, 3, 7):
				cell.alignment = Alignment(horizontal="center", vertical="center")
			elif col_idx == 5:
				cell.alignment = Alignment(horizontal="right", vertical="center")
				cell.number_format = amount_fmt
			else:
				cell.alignment = Alignment(horizontal="left", vertical="center")

	last_data_row = data_start_row + max(len(items), 1) - 1
	total_row = last_data_row + 1

	total_amount = flt(doc.tong_thuc_linh)
	ws.cell(row=total_row, column=4, value="Tổng cộng")
	ws.cell(row=total_row, column=5, value=total_amount)

	for col_idx in range(1, 10):
		cell = ws.cell(row=total_row, column=col_idx)
		cell.border = thin_border
		cell.fill = total_fill
		cell.font = Font(bold=True, size=12)
		if col_idx == 5:
			cell.alignment = Alignment(horizontal="right", vertical="center")
			cell.number_format = amount_fmt
		elif col_idx == 4:
			cell.alignment = Alignment(horizontal="left", vertical="center")
		else:
			cell.alignment = Alignment(horizontal="center", vertical="center")

	date_row = total_row + 1
	ws.merge_cells(start_row=date_row, start_column=7, end_row=date_row, end_column=9)
	ws.cell(row=date_row, column=7, value=f"Hà Nội, ngày      tháng      năm {year_text}")
	ws.cell(row=date_row, column=7).alignment = Alignment(horizontal="right", vertical="center")
	ws.cell(row=date_row, column=7).font = Font(italic=True, color="FF0000", size=12)

	text_row = total_row + 2
	amount_in_words = _number_to_words_vnd(total_amount)
	ws.merge_cells(start_row=text_row, start_column=1, end_row=text_row, end_column=5)
	ws.cell(row=text_row, column=1, value=f"(Bằng chữ: {amount_in_words})")
	ws.cell(row=text_row, column=1).font = Font(italic=True, bold=True, size=12)
	ws.cell(row=text_row, column=1).fill = yellow_fill
	ws.cell(row=text_row, column=1).alignment = Alignment(horizontal="left", vertical="center")

	sign_title_row = total_row + 4
	sign_name_row = total_row + 12

	ws.merge_cells(start_row=sign_title_row, start_column=2, end_row=sign_title_row, end_column=4)
	ws.cell(row=sign_title_row, column=2, value="KẾ TOÁN TRƯỞNG")
	ws.cell(row=sign_title_row, column=2).font = Font(bold=True, size=14)
	ws.cell(row=sign_title_row, column=2).alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells(start_row=sign_title_row, start_column=7, end_row=sign_title_row, end_column=9)
	ws.cell(row=sign_title_row, column=7, value="TỔNG GIÁM ĐỐC")
	ws.cell(row=sign_title_row, column=7).font = Font(bold=True, size=14)
	ws.cell(row=sign_title_row, column=7).alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells(start_row=sign_name_row, start_column=2, end_row=sign_name_row, end_column=4)
	ws.cell(row=sign_name_row, column=2, value="Nguyễn Ngọc Cách")
	ws.cell(row=sign_name_row, column=2).font = Font(bold=True, size=13)
	ws.cell(row=sign_name_row, column=2).alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells(start_row=sign_name_row, start_column=7, end_row=sign_name_row, end_column=9)
	ws.cell(row=sign_name_row, column=7, value="Cao Hữu Hiếu")
	ws.cell(row=sign_name_row, column=7).font = Font(bold=True, size=13)
	ws.cell(row=sign_name_row, column=7).alignment = Alignment(horizontal="center", vertical="center")

	ws.freeze_panes = "A8"


def _append_pc_chqs_ds_chi_sheet(
	workbook: Workbook,
	doc: Document,
	items: List[Document],
	employee_info_map: Dict[str, Dict[str, str]],
	month_label: str,
	year_label: str,
):
	"""Append DS chi sheet for allowance type PC Ban CHQS."""
	ws = workbook.create_sheet("DS chi")

	column_widths = {
		"A": 6,
		"B": 24,
		"C": 10,
		"D": 22,
		"E": 16,
		"F": 40,
		"G": 18,
		"H": 14,
		"I": 14,
	}
	for col, width in column_widths.items():
		ws.column_dimensions[col].width = width

	thin_side = Side(style="thin", color="000000")
	thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
	total_fill = PatternFill("solid", fgColor="92D050")
	yellow_fill = PatternFill("solid", fgColor="FFF200")

	company_title = "TẬP ĐOÀN DỆT MAY VIỆT NAM"
	branch_title = ((doc.branch or "").strip() or "VĂN PHÒNG 1").upper()
	year_text = year_label or str(cint(doc.year) or "")
	month_tokens = _extract_valid_month_tokens(doc.month)
	ref_month = f"{month_tokens[0]:02d}" if month_tokens else (month_label.split(",")[0] if month_label else "")

	ws.merge_cells("A1:C1")
	ws["A1"] = company_title
	ws["A1"].font = Font(size=13)

	ws.merge_cells("A2:C2")
	ws["A2"] = branch_title
	ws["A2"].font = Font(bold=True, size=13)
	ws["A2"].alignment = Alignment(horizontal="left", vertical="center")

	ws.merge_cells("B3:F3")
	ws["B3"] = f"BẢNG THANH TOÁN CHI PHỤ CẤP CHQS THÁNG {month_label}/{year_text}"
	ws["B3"].font = Font(bold=True, size=15)
	ws["B3"].alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells("G3:H3")
	ws["G3"] = "Số tham chiếu LTT:"
	ws["G3"].font = Font(bold=True, size=12)
	ws["G3"].alignment = Alignment(horizontal="center", vertical="center")

	ws["I3"] = f"-{ref_month}/{year_text}-"
	ws["I3"].font = Font(bold=True, size=12)
	ws["I3"].alignment = Alignment(horizontal="center", vertical="center")

	headers = [
		"TT",
		"Số tài khoản",
		"Loại tiền",
		"Tên Người hưởng",
		"Số tiền",
		"Nội dung",
		"Chuyển tiền nhanh\n24/7/ Chuyển tiền\nthường ngoài VCB",
		"Tại ngân hàng",
		"Ghi chú",
	]
	header_start_row = 6
	header_end_row = 7

	for idx, label in enumerate(headers, start=1):
		ws.merge_cells(
			start_row=header_start_row,
			start_column=idx,
			end_row=header_end_row,
			end_column=idx,
		)
		cell = ws.cell(row=header_start_row, column=idx)
		cell.value = label
		cell.font = Font(bold=True, size=12)
		cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
		cell.border = thin_border
		ws.cell(row=header_end_row, column=idx).border = thin_border

	ws.row_dimensions[header_start_row].height = 24
	ws.row_dimensions[header_end_row].height = 44

	data_start_row = 8
	content_template = _build_chqs_ds_chi_content(doc.month)
	amount_fmt = '#,##0;[Red]-#,##0;"-"'

	for idx, row in enumerate(items, start=1):
		current_row = data_start_row + idx - 1
		emp_info = employee_info_map.get(row.employee) or {}
		bank_name = (emp_info.get("bank_name") or "").strip()
		transfer_mode = "N" if (bank_name and "VCB" not in bank_name.upper()) else ""

		row_data = [
			idx,
			(emp_info.get("bank_ac_no") or "").strip(),
			"VND",
			_to_upper_no_accents(emp_info.get("employee_name") or row.employee or ""),
			flt(row.thuc_linh),
			content_template,
			transfer_mode,
			bank_name,
			"",
		]

		for col_idx, value in enumerate(row_data, start=1):
			cell = ws.cell(row=current_row, column=col_idx, value=value)
			cell.border = thin_border
			if col_idx in (1, 3, 7):
				cell.alignment = Alignment(horizontal="center", vertical="center")
			elif col_idx == 5:
				cell.alignment = Alignment(horizontal="right", vertical="center")
				cell.number_format = amount_fmt
			else:
				cell.alignment = Alignment(horizontal="left", vertical="center")

	last_data_row = data_start_row + max(len(items), 1) - 1
	total_row = last_data_row + 1

	total_amount = flt(doc.tong_thuc_linh)
	ws.cell(row=total_row, column=4, value="Tổng cộng")
	ws.cell(row=total_row, column=5, value=total_amount)

	for col_idx in range(1, 10):
		cell = ws.cell(row=total_row, column=col_idx)
		cell.border = thin_border
		cell.fill = total_fill
		cell.font = Font(bold=True, size=12)
		if col_idx == 5:
			cell.alignment = Alignment(horizontal="right", vertical="center")
			cell.number_format = amount_fmt
		elif col_idx == 4:
			cell.alignment = Alignment(horizontal="left", vertical="center")
		else:
			cell.alignment = Alignment(horizontal="center", vertical="center")

	date_row = total_row + 1
	ws.merge_cells(start_row=date_row, start_column=7, end_row=date_row, end_column=9)
	ws.cell(row=date_row, column=7, value=f"Hà Nội, ngày      tháng      năm {year_text}")
	ws.cell(row=date_row, column=7).alignment = Alignment(horizontal="right", vertical="center")
	ws.cell(row=date_row, column=7).font = Font(italic=True, color="FF0000", size=12)

	text_row = total_row + 2
	amount_in_words = _number_to_words_vnd(total_amount)
	ws.merge_cells(start_row=text_row, start_column=1, end_row=text_row, end_column=5)
	ws.cell(row=text_row, column=1, value=f"(Bằng chữ: {amount_in_words})")
	ws.cell(row=text_row, column=1).font = Font(italic=True, bold=True, size=12)
	ws.cell(row=text_row, column=1).fill = yellow_fill
	ws.cell(row=text_row, column=1).alignment = Alignment(horizontal="left", vertical="center")

	sign_title_row = total_row + 4
	sign_name_row = total_row + 12

	ws.merge_cells(start_row=sign_title_row, start_column=2, end_row=sign_title_row, end_column=4)
	ws.cell(row=sign_title_row, column=2, value="KẾ TOÁN TRƯỞNG")
	ws.cell(row=sign_title_row, column=2).font = Font(bold=True, size=14)
	ws.cell(row=sign_title_row, column=2).alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells(start_row=sign_title_row, start_column=7, end_row=sign_title_row, end_column=9)
	ws.cell(row=sign_title_row, column=7, value="TỔNG GIÁM ĐỐC")
	ws.cell(row=sign_title_row, column=7).font = Font(bold=True, size=14)
	ws.cell(row=sign_title_row, column=7).alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells(start_row=sign_name_row, start_column=2, end_row=sign_name_row, end_column=4)
	ws.cell(row=sign_name_row, column=2, value="Nguyễn Ngọc Cách")
	ws.cell(row=sign_name_row, column=2).font = Font(bold=True, size=13)
	ws.cell(row=sign_name_row, column=2).alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells(start_row=sign_name_row, start_column=7, end_row=sign_name_row, end_column=9)
	ws.cell(row=sign_name_row, column=7, value="Cao Hữu Hiếu")
	ws.cell(row=sign_name_row, column=7).font = Font(bold=True, size=13)
	ws.cell(row=sign_name_row, column=7).alignment = Alignment(horizontal="center", vertical="center")

	ws.freeze_panes = "A8"


def _append_pc_cds_ds_chi_sheet(
	workbook: Workbook,
	doc: Document,
	items: List[Document],
	employee_info_map: Dict[str, Dict[str, str]],
	month_label: str,
	year_label: str,
):
	"""Append DS Chi sheet for PC CĐS payout."""
	ws = workbook.create_sheet("DS Chi")

	column_widths = {
		"A": 6,
		"B": 24,
		"C": 10,
		"D": 22,
		"E": 16,
		"F": 34,
		"G": 18,
		"H": 14,
		"I": 14,
	}
	for col, width in column_widths.items():
		ws.column_dimensions[col].width = width

	thin_side = Side(style="thin", color="000000")
	thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
	total_fill = PatternFill("solid", fgColor="92D050")
	yellow_fill = PatternFill("solid", fgColor="FFF200")

	company_title = "TẬP ĐOÀN DỆT MAY VIỆT NAM"
	branch_title = ((doc.branch or "").strip() or "VĂN PHÒNG 1").upper()
	year_text = year_label or str(cint(doc.year) or "")

	ws.merge_cells("A1:C1")
	ws["A1"] = company_title
	ws["A1"].font = Font(size=13)

	ws.merge_cells("A2:C2")
	ws["A2"] = branch_title
	ws["A2"].font = Font(bold=True, size=13)
	ws["A2"].alignment = Alignment(horizontal="left", vertical="center")

	ws.merge_cells("B3:F3")
	ws["B3"] = f"BẢNG THANH TOÁN CHI PHỤ CẤP CHUYỂN ĐỔI SỐ THÁNG {month_label}/{year_text}"
	ws["B3"].font = Font(bold=True, size=15)
	ws["B3"].alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells("G3:H3")
	ws["G3"] = "Số tham chiếu LTT:"
	ws["G3"].font = Font(bold=True, size=12)
	ws["G3"].alignment = Alignment(horizontal="center", vertical="center")

	ws["I3"] = f"-{month_label}/{year_text}-"
	ws["I3"].font = Font(bold=True, size=12)
	ws["I3"].alignment = Alignment(horizontal="center", vertical="center")

	headers = [
		"TT",
		"Số tài khoản",
		"Loại tiền",
		"Tên Người hưởng",
		"Số tiền",
		"Nội dung",
		"Chuyển tiền nhanh\n24/7/ Chuyển tiền\nthường ngoài VCB",
		"Tại ngân hàng",
		"Ghi chú",
	]
	header_start_row = 6
	header_end_row = 7

	for idx, label in enumerate(headers, start=1):
		ws.merge_cells(
			start_row=header_start_row,
			start_column=idx,
			end_row=header_end_row,
			end_column=idx,
		)
		cell = ws.cell(row=header_start_row, column=idx)
		cell.value = label
		cell.font = Font(bold=True, size=12)
		cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
		cell.border = thin_border
		ws.cell(row=header_end_row, column=idx).border = thin_border

	ws.row_dimensions[header_start_row].height = 24
	ws.row_dimensions[header_end_row].height = 44

	data_start_row = 8
	payout_month_text = (doc.month or month_label or "").strip()
	content_template = f"Vinatex chi phụ cấp Chuyển đổi số tháng {payout_month_text}/{year_text}"
	amount_fmt = '#,##0;[Red]-#,##0;"-"'

	for idx, row in enumerate(items, start=1):
		current_row = data_start_row + idx - 1
		emp_info = employee_info_map.get(row.employee) or {}
		bank_name = (emp_info.get("bank_name") or "").strip()
		transfer_mode = "N" if (bank_name and "VCB" not in bank_name.upper()) else ""

		row_data = [
			idx,
			(emp_info.get("bank_ac_no") or "").strip(),
			"VND",
			_to_upper_no_accents(emp_info.get("employee_name") or row.employee or ""),
			flt(row.thuc_linh),
			content_template,
			transfer_mode,
			bank_name,
			"",
		]

		for col_idx, value in enumerate(row_data, start=1):
			cell = ws.cell(row=current_row, column=col_idx, value=value)
			cell.border = thin_border
			if col_idx in (1, 3, 7):
				cell.alignment = Alignment(horizontal="center", vertical="center")
			elif col_idx == 5:
				cell.alignment = Alignment(horizontal="right", vertical="center")
				cell.number_format = amount_fmt
			else:
				cell.alignment = Alignment(horizontal="left", vertical="center")

	last_data_row = data_start_row + max(len(items), 1) - 1
	total_row = last_data_row + 1

	total_amount = flt(doc.tong_thuc_linh)
	ws.cell(row=total_row, column=4, value="Tổng cộng")
	ws.cell(row=total_row, column=5, value=total_amount)

	for col_idx in range(1, 10):
		cell = ws.cell(row=total_row, column=col_idx)
		cell.border = thin_border
		cell.fill = total_fill
		cell.font = Font(bold=True, size=12)
		if col_idx == 5:
			cell.alignment = Alignment(horizontal="right", vertical="center")
			cell.number_format = amount_fmt
		elif col_idx == 4:
			cell.alignment = Alignment(horizontal="left", vertical="center")
		else:
			cell.alignment = Alignment(horizontal="center", vertical="center")

	date_row = total_row + 1
	ws.merge_cells(start_row=date_row, start_column=7, end_row=date_row, end_column=9)
	ws.cell(row=date_row, column=7, value=f"Hà Nội, ngày      tháng      năm {year_text}")
	ws.cell(row=date_row, column=7).alignment = Alignment(horizontal="right", vertical="center")
	ws.cell(row=date_row, column=7).font = Font(italic=True, color="FF0000", size=12)

	text_row = total_row + 2
	amount_in_words = _number_to_words_vnd(total_amount)
	ws.merge_cells(start_row=text_row, start_column=1, end_row=text_row, end_column=5)
	ws.cell(row=text_row, column=1, value=f"(Bằng chữ: {amount_in_words})")
	ws.cell(row=text_row, column=1).font = Font(italic=True, bold=True, size=12)
	ws.cell(row=text_row, column=1).fill = yellow_fill
	ws.cell(row=text_row, column=1).alignment = Alignment(horizontal="left", vertical="center")

	sign_title_row = total_row + 4
	sign_name_row = total_row + 12

	ws.merge_cells(start_row=sign_title_row, start_column=2, end_row=sign_title_row, end_column=4)
	ws.cell(row=sign_title_row, column=2, value="KẾ TOÁN TRƯỞNG")
	ws.cell(row=sign_title_row, column=2).font = Font(bold=True, size=14)
	ws.cell(row=sign_title_row, column=2).alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells(start_row=sign_title_row, start_column=7, end_row=sign_title_row, end_column=9)
	ws.cell(row=sign_title_row, column=7, value="TỔNG GIÁM ĐỐC")
	ws.cell(row=sign_title_row, column=7).font = Font(bold=True, size=14)
	ws.cell(row=sign_title_row, column=7).alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells(start_row=sign_name_row, start_column=2, end_row=sign_name_row, end_column=4)
	ws.cell(row=sign_name_row, column=2, value="Nguyễn Ngọc Cách")
	ws.cell(row=sign_name_row, column=2).font = Font(bold=True, size=13)
	ws.cell(row=sign_name_row, column=2).alignment = Alignment(horizontal="center", vertical="center")

	ws.merge_cells(start_row=sign_name_row, start_column=7, end_row=sign_name_row, end_column=9)
	ws.cell(row=sign_name_row, column=7, value="Cao Hữu Hiếu")
	ws.cell(row=sign_name_row, column=7).font = Font(bold=True, size=13)
	ws.cell(row=sign_name_row, column=7).alignment = Alignment(horizontal="center", vertical="center")

	ws.freeze_panes = "A8"


def _get_employee_info_map(items: List[Document]) -> Dict[str, Dict[str, str]]:
	employee_codes = sorted({row.employee for row in items if row.employee})
	if not employee_codes:
		return {}
	employees = frappe.get_all(
		"Employee",
		filters={"name": ("in", employee_codes)},
		fields=["name", "employee_name", "bank_ac_no", "bank_name", "department"],
		limit_page_length=0,
	)
	return {
		d.name: {
			"employee_name": d.employee_name or "",
			"bank_ac_no": d.bank_ac_no or "",
			"bank_name": d.bank_name or "",
			"department": d.department or "",
		}
		for d in employees
	}


def _resolve_preparer_name(
	doc: Document, employee_info_map: Dict[str, Dict[str, str]] | None = None
) -> str:
	employee_code = (doc.employee or "").strip()
	if not employee_code:
		return ""

	info_map = employee_info_map or {}
	info = info_map.get(employee_code) or {}
	if info.get("employee_name"):
		return info.get("employee_name")

	employee_name = frappe.db.get_value("Employee", employee_code, "employee_name")
	return employee_name or employee_code


def _to_upper_no_accents(value: str | None) -> str:
	text = (value or "").strip()
	if not text:
		return ""
	text = text.replace("Đ", "D").replace("đ", "d")
	normalized = unicodedata.normalize("NFD", text)
	no_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
	return no_accents.upper()


def _number_to_words_vnd(amount: float | int) -> str:
	"""Convert an amount to Vietnamese words in VND with explicit hundred in middle groups."""
	value = int(round(flt(amount)))
	if value == 0:
		return "Không đồng"

	negative = value < 0
	value = abs(value)

	triplets = []
	while value > 0:
		triplets.append(value % 1000)
		value //= 1000

	highest_idx = max((i for i, v in enumerate(triplets) if v > 0), default=0)
	parts = []
	for idx in range(highest_idx, -1, -1):
		triplet = triplets[idx]
		if triplet == 0:
			continue
		force_full_hundreds = idx < highest_idx and triplet < 100
		triplet_words = _read_triplet_vn(triplet, force_full_hundreds)
		group_unit = _triplet_group_unit(idx)
		parts.append(f"{triplet_words} {group_unit}".strip())

	joined = " ".join(parts).strip()
	if joined:
		joined = joined[0].upper() + joined[1:]
	result = f"{joined} đồng"
	if negative:
		result = f"Âm {result}"
	return result


def _read_triplet_vn(n: int, force_full_hundreds: bool = False) -> str:
	digits = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
	hundreds = n // 100
	tens = (n % 100) // 10
	units = n % 10

	parts = []
	if hundreds > 0 or force_full_hundreds:
		parts.extend([digits[hundreds], "trăm"])

	if tens > 1:
		parts.extend([digits[tens], "mươi"])
		if units == 1:
			parts.append("mốt")
		elif units == 5:
			parts.append("lăm")
		elif units > 0:
			parts.append(digits[units])
	elif tens == 1:
		parts.append("mười")
		if units == 5:
			parts.append("lăm")
		elif units > 0:
			parts.append(digits[units])
	elif units > 0:
		if hundreds > 0 or force_full_hundreds:
			parts.append("linh")
		parts.append(digits[units])

	return " ".join(parts).strip()


def _triplet_group_unit(index: int) -> str:
	# 0: "", 1: nghìn, 2: triệu, 3: tỷ, 4: nghìn tỷ, 5: triệu tỷ, 6: tỷ tỷ...
	small_units = ["", "nghìn", "triệu"]
	level = index // 3
	base = small_units[index % 3]
	if level == 0:
		return base
	if level == 1:
		return f"{base} tỷ".strip()
	return f"{base} {' '.join(['tỷ'] * level)}".strip()


def _resolve_month_label(value: str | None) -> str:
	raw = (value or "").strip()
	if not raw:
		return ""
	tokens = re.findall(r"\d+", raw)
	if not tokens:
		return raw
	if len(tokens) == 1:
		month_num = cint(tokens[0])
		if 1 <= month_num <= 12:
			return f"{month_num:02d}"
	return ",".join(tokens)


def _normalize_allowance_type_key(value: str | None) -> str:
	raw = _to_upper_no_accents(value)
	if not raw:
		return ""
	return re.sub(r"\s+", " ", raw).strip()


def _resolve_salary_parameter_effective_date(
	target_date: str | None = None, month: str | None = None, year: int | str | None = None
):
	year_num = cint(year)
	month_tokens = _extract_valid_month_tokens(month)
	if year_num and month_tokens:
		month_num = month_tokens[-1]
		period_start = getdate(f"{year_num}-{month_num:02d}-01")
		return get_last_day(period_start)
	if target_date:
		return getdate(target_date)
	return getdate(today())


def _build_dac_thu_period_title(month_value: str | None, year_value: str) -> str:
	raw = (month_value or "").strip()
	tokens = _extract_valid_month_tokens(month_value)
	if not tokens:
		return f"THÁNG {raw or '...'} NĂM {year_value or '...'}"
	if len(tokens) == 1:
		return f"THÁNG {tokens[0]:02d} NĂM {year_value or '...'}"
	if len(tokens) == 2:
		return f"THÁNG {tokens[0]:02d} VÀ THÁNG {tokens[1]:02d} NĂM {year_value or '...'}"
	return f"TỪ THÁNG {tokens[0]:02d} ĐẾN THÁNG {tokens[-1]:02d} NĂM {year_value or '...'}"


def _build_dac_thu_month_header(month_num: int | None, year_label: str) -> str:
	if month_num and 1 <= month_num <= 12:
		return f"Tháng {month_num:02d}/{year_label or '...'}"
	return "Tháng .../..."


def _build_dac_thu_ds_chi_content(month_value: str | None) -> str:
	tokens = _extract_valid_month_tokens(month_value)
	if len(tokens) >= 2:
		return f"Vinatex chi phụ cấp đặc thù tháng {tokens[-1]:02d}, tháng {tokens[-2]:02d}"
	if len(tokens) == 1:
		current_month = tokens[0]
		prev_month = 12 if current_month == 1 else current_month - 1
		return f"Vinatex chi phụ cấp đặc thù tháng {current_month:02d}, tháng {prev_month:02d}"
	raw = (month_value or "").strip()
	return f"Vinatex chi phụ cấp đặc thù tháng {raw or '...'}"


def _categorize_dac_thu_group(department: str | None) -> str:
	dept_key = _normalize_allowance_type_key(department)
	if "HOI DONG QUAN TRI" in dept_key or "HDQT" in dept_key:
		return "HDQT"
	if "DIEU HANH" in dept_key:
		return "CQDH"
	return "BAN"


def _build_chqs_period_title(month_value: str | None, year_value: str) -> str:
	raw = (month_value or "").strip()
	tokens = _extract_valid_month_tokens(month_value)

	if not tokens:
		return f"THÁNG {raw or '...'} NĂM {year_value or '...'}"
	if len(tokens) == 1:
		return f"THÁNG {tokens[0]:02d} NĂM {year_value or '...'}"
	if len(tokens) == 2:
		return f"TỪ THÁNG {tokens[0]:02d} VÀ THÁNG {tokens[1]:02d} NĂM {year_value or '...'}"
	return f"TỪ THÁNG {tokens[0]:02d} ĐẾN THÁNG {tokens[-1]:02d} NĂM {year_value or '...'}"


def _build_chqs_ds_chi_content(month_value: str | None) -> str:
	tokens = _extract_valid_month_tokens(month_value)
	if not tokens:
		raw = (month_value or "").strip()
		return f"Vinatex chi phụ cấp Ban CHQS tháng {raw or '...'}"
	if len(tokens) == 1:
		return f"Vinatex chi phụ cấp Ban CHQS tháng {tokens[0]:02d}"
	month_text = ", ".join([f"tháng {m:02d}" for m in tokens])
	return f"Vinatex chi phụ cấp Ban CHQS {month_text}"


def _extract_valid_month_tokens(month_value: str | None) -> List[int]:
	raw = (month_value or "").strip()
	tokens: List[int] = []
	for token in re.findall(r"\d+", raw):
		month_num = cint(token)
		if 1 <= month_num <= 12 and month_num not in tokens:
			tokens.append(month_num)
	return tokens
