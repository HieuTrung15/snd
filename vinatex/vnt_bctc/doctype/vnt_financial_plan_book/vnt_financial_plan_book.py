# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import re
import json
import unicodedata
from io import BytesIO

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate
from frappe.utils.xlsxutils import make_xlsx
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl import load_workbook

class VNTFinancialPlanBook(Document):
	pass


@frappe.whitelist()
def get_template_items(template):
	if not template:
		frappe.throw(_("Vui lòng chọn Mẫu báo cáo."))

	doc = frappe.get_doc("VNT Financial Report Template", template)
	items = []
	for field in doc.meta.fields:
		if field.fieldtype != "Table":
			continue
		if field.options != "VNT Financial Report Template Item":
			continue
		for row in doc.get(field.fieldname) or []:
			items.append(
				{
					"doi_tuong": row.doi_tuong,
					"ct_doi_tuong": row.ct_doi_tuong,
					"chi_tiet_doi_tuong_c2": row.chi_tiet_doi_tuong_c2,
					"khoan_muc": row.khoan_muc,
					"ct": row.ct,
				}
			)
	return items


@frappe.whitelist()
def get_grouped_plan_book_data(docname=None):
	if not docname:
		frappe.throw(_("Thiếu sổ kế hoạch để tải dữ liệu."))

	doc = frappe.get_doc("VNT Financial Plan Book", docname)
	if not doc.template:
		frappe.throw(_("Sổ kế hoạch chưa có Mẫu báo cáo."))

	template = frappe.get_doc("VNT Financial Report Template", doc.template)
	value_map = {}
	for line in doc.lines:
		key = _build_line_key(
			line.doi_tuong,
			line.ct_doi_tuong,
			line.chi_tiet_doi_tuong_c2,
			line.khoan_muc,
			line.ct,
		)
		value_map[key] = line

	groups = []
	for field in template.meta.fields:
		if field.fieldtype != "Table":
			continue
		if field.options != "VNT Financial Report Template Item":
			continue
		items = []
		for row in template.get(field.fieldname) or []:
			key = _build_line_key(
				row.doi_tuong,
				row.ct_doi_tuong,
				row.chi_tiet_doi_tuong_c2,
				row.khoan_muc,
				row.ct,
			)
			line = value_map.get(key)
			items.append(
				{
					"doi_tuong": row.doi_tuong,
					"ct_doi_tuong": row.ct_doi_tuong,
					"chi_tiet_doi_tuong_c2": row.chi_tiet_doi_tuong_c2,
					"khoan_muc": row.khoan_muc,
					"ct": row.ct,
					"annual_plan_value": line.annual_plan_value if line else None,
					"plan_3t": line.plan_3t if line else None,
					"plan_6t": line.plan_6t if line else None,
					"plan_9t": line.plan_9t if line else None,
					"plan_12t": line.plan_12t if line else None,
				}
			)
		groups.append(
			{
				"label": field.label or field.fieldname,
				"fieldname": field.fieldname,
				"items": items,
			}
		)

	return {
		"doc": {
			"name": doc.name,
			"company": doc.company,
			"fiscal_year": doc.fiscal_year,
			"template": doc.template,
			"scenario": doc.scenario,
			"status": doc.status,
		},
		"groups": groups,
	}


@frappe.whitelist()
def save_grouped_plan_book(docname=None, lines=None):
	if not docname:
		frappe.throw(_("Thiếu sổ kế hoạch để lưu dữ liệu."))
	if lines is None:
		frappe.throw(_("Thiếu dữ liệu để lưu."))

	if isinstance(lines, str):
		lines = json.loads(lines)

	doc = frappe.get_doc("VNT Financial Plan Book", docname)
	doc.set("lines", [])
	for line in lines:
		doc.append(
			"lines",
			{
				"doi_tuong": line.get("doi_tuong"),
				"ct_doi_tuong": line.get("ct_doi_tuong"),
				"chi_tiet_doi_tuong_c2": line.get("chi_tiet_doi_tuong_c2"),
				"khoan_muc": line.get("khoan_muc"),
				"ct": line.get("ct"),
				"annual_plan_value": _to_number(line.get("annual_plan_value")),
				"plan_3t": _to_number(line.get("plan_3t")),
				"plan_6t": _to_number(line.get("plan_6t")),
				"plan_9t": _to_number(line.get("plan_9t")),
				"plan_12t": _to_number(line.get("plan_12t")),
			},
		)
	doc.save()
	return {"name": doc.name}


@frappe.whitelist()
def create_plan_book(company=None, fiscal_year=None, template=None, scenario="Kế hoạch", version_no=None):
	if not (company and fiscal_year and template):
		frappe.throw(_("Thiếu thông tin để tạo sổ kế hoạch."))

	template_doc = frappe.get_doc("VNT Financial Report Template", template)

	doc = frappe.new_doc("VNT Financial Plan Book")
	doc.company = company
	doc.fiscal_year = fiscal_year
	doc.template = template
	doc.scenario = scenario or "Kế hoạch"
	doc.version_no = version_no
	doc.status = "Nháp"
	doc.is_active = 1

	lines = []
	for field in template_doc.meta.fields:
		if field.fieldtype != "Table":
			continue
		if field.options != "VNT Financial Report Template Item":
			continue
		for row in template_doc.get(field.fieldname) or []:
			lines.append(
				{
					"doi_tuong": row.doi_tuong,
					"ct_doi_tuong": row.ct_doi_tuong,
					"chi_tiet_doi_tuong_c2": row.chi_tiet_doi_tuong_c2,
					"khoan_muc": row.khoan_muc,
					"ct": row.ct,
					"annual_plan_value": None,
					"plan_3t": None,
					"plan_6t": None,
					"plan_9t": None,
					"plan_12t": None,
				}
			)
	doc.set("lines", lines)
	doc.insert()
	return {"name": doc.name}


@frappe.whitelist()
def download_plan_book_excel(docname=None):
	if not docname:
		frappe.throw(_("Thiếu tham chiếu sổ kế hoạch để tải xuống."))

	doc = frappe.get_doc("VNT Financial Plan Book", docname)
	headers = [
		"Mã khoản mục",
		"Tên khoản mục",
		"Nhóm",
		"Loại dòng",
		"Loại khoản mục",
		"KH năm",
		"3T",
		"6T",
		"9T",
		"12T",
		"Thứ tự",
		"Ghi chú",
	]
	data = [headers]
	for line in doc.lines:
		data.append(
			[
				line.item_code,
				line.item_name,
				line.group_name,
				line.row_kind,
				line.item_type,
				line.annual_plan_value,
				line.plan_3t,
				line.plan_6t,
				line.plan_9t,
				line.plan_12t,
				line.sort_order,
				line.note,
			]
		)

	

	xlsx_file = make_xlsx(data, "Ke hoach nam")
	frappe.response["filename"] = f"{docname}.xlsx"
	frappe.response["filecontent"] = xlsx_file.getvalue()
	frappe.response["type"] = "binary"


@frappe.whitelist()
def import_plan_book_excel(docname=None, file_url=None):
	if not docname:
		frappe.throw(_("Thiếu tham chiếu sổ kế hoạch để nhập dữ liệu."))
	if not file_url:
		frappe.throw(_("Vui lòng chọn tệp Excel để nhập."))

	doc = frappe.get_doc("VNT Financial Plan Book", docname)

	rows = read_xlsx_file_from_attached_file(file_url=file_url)
	if not rows:
		frappe.throw(_("Không tìm thấy dữ liệu trong tệp Excel."))

	header_map = _build_header_map(rows[0])
	if "item_code" not in header_map:
		frappe.throw(_("Thiếu cột \"Mã khoản mục\" trong tệp Excel."))

	existing = {line.item_code: line for line in doc.lines if line.item_code}
	added = 0
	updated = 0

	for row in rows[1:]:
		if not row or all(cell is None for cell in row):
			continue
		item_code = _cell(row, header_map.get("item_code"))
		if not item_code:
			continue
		item_code = str(item_code).strip()
		if not item_code:
			continue

		line = existing.get(item_code)
		if not line:
			line = doc.append("lines", {})
			line.item_code = item_code
			existing[item_code] = line
			added += 1
		else:
			updated += 1

		line.item_name = _cell(row, header_map.get("item_name"))
		line.group_name = _cell(row, header_map.get("group_name"))
		row_kind = _normalize_select_value(_cell(row, header_map.get("row_kind")), _ROW_KIND_MAP)
		item_type = _normalize_select_value(_cell(row, header_map.get("item_type")), _ITEM_TYPE_MAP)
		line.row_kind = row_kind or line.row_kind
		line.item_type = item_type or line.item_type
		annual_value = _cell(row, header_map.get("annual_plan_value"))
		line.annual_plan_value = flt(annual_value) if annual_value not in (None, "") else None
		line.plan_3t = _to_number(_cell(row, header_map.get("plan_3t")))
		line.plan_6t = _to_number(_cell(row, header_map.get("plan_6t")))
		line.plan_9t = _to_number(_cell(row, header_map.get("plan_9t")))
		line.plan_12t = _to_number(_cell(row, header_map.get("plan_12t")))
		line.sort_order = _coerce_int(_cell(row, header_map.get("sort_order")))
		line.note = _cell(row, header_map.get("note"))

	doc.save()
	return {"added": added, "updated": updated}


def _build_header_map(headers):
	mapping = {}
	for idx, header in enumerate(headers or []):
		key = _normalize_header(header)
		if key in {"ma khoan muc", "item code"}:
			mapping["item_code"] = idx
		elif key in {"ten khoan muc", "item name"}:
			mapping["item_name"] = idx
		elif key in {"nhom", "group"}:
			mapping["group_name"] = idx
		elif key in {"loai dong", "row kind"}:
			mapping["row_kind"] = idx
		elif key in {"loai khoan muc", "item type"}:
			mapping["item_type"] = idx
		elif key in {"kh nam", "ke hoach nam", "gia tri ke hoach nam", "annual plan value"}:
			mapping["annual_plan_value"] = idx
		elif key == "3t":
			mapping["plan_3t"] = idx
		elif key == "6t":
			mapping["plan_6t"] = idx
		elif key == "9t":
			mapping["plan_9t"] = idx
		elif key == "12t":
			mapping["plan_12t"] = idx
		elif key in {"thu tu", "sort order"}:
			mapping["sort_order"] = idx
		elif key in {"ghi chu", "note"}:
			mapping["note"] = idx
	return mapping


def _cell(row, index):
	if index is None:
		return None
	if index >= len(row):
		return None
	return row[index]


def _coerce_int(value):
	try:
		if value is None or value == "":
			return None
		return int(value)
	except (TypeError, ValueError):
		return None


def _normalize_select_value(value, mapping):
	if value is None or value == "":
		return None
	key = str(value).strip()
	return mapping.get(key, key)


def _normalize_header(value):
	text = (value or "").strip().lower()
	text = unicodedata.normalize("NFKD", text)
	return "".join(char for char in text if not unicodedata.combining(char))


def _to_number(value):
	if value in (None, ""):
		return None
	return flt(value)


_ROW_KIND_MAP = {
	"Group Header": "Tiêu đề nhóm",
	"Normal": "Bình thường",
	"Subtotal": "Cộng nhóm",
	"Grand Total": "Tổng cộng",
}

_ITEM_TYPE_MAP = {
	"Input": "Nhập liệu",
	"Calculated": "Tính toán",
}



@frappe.whitelist()
def download_matrix_excel(docname=None, template=None):
	if not docname:
		frappe.throw(_("Thiếu tham chiếu sổ kế hoạch để tải xuống."))

	is_template = cint(template)
	doc = frappe.get_doc("VNT Financial Plan Book", docname)
	fy_doc, current_year = _get_fiscal_year_info(doc.fiscal_year)
	prev_fy_name, prev_year = _get_previous_fiscal_year(fy_doc)
	prev_book = _find_previous_book(doc, prev_fy_name)

	lines = _get_sorted_lines(doc)
	if is_template:
		annual_current = {}
		annual_prev = {}
		plan_quarters_prev = {}
		plan_quarters_current = {}
		actual_prev = {}
		actual_current = {}
	else:
		annual_current = {line.item_code: line.annual_plan_value for line in doc.lines if line.item_code}
		annual_prev = {}
		if prev_book:
			annual_prev = {
				line.item_code: line.annual_plan_value for line in prev_book.lines if line.item_code
			}

		plan_quarters_prev = _build_plan_quarters(prev_book)
		plan_quarters_current = _build_plan_quarters(doc)
		actual_prev = _get_monthly_item_values(
			prev_book.name if prev_book else None,
			prev_year,
			"monthly_value",
		)
		actual_current = _get_monthly_item_values(doc.name, current_year, "monthly_value")

	headers = _build_matrix_headers(prev_year, current_year)
	column_widths = _build_matrix_column_widths(len(headers))

	plan_rows = _build_matrix_rows(
		lines,
		annual_prev,
		annual_current,
		{},
		{},
		prev_year,
		current_year,
		quarter_prev=plan_quarters_prev,
		quarter_current=plan_quarters_current,
		use_formulas=is_template,
	)
	actual_rows = _build_matrix_rows(
		lines,
		annual_prev,
		annual_current,
		actual_prev,
		actual_current,
		prev_year,
		current_year,
		use_formulas=is_template,
	)

	xlsx_file = _build_matrix_workbook(headers, plan_rows, actual_rows, column_widths)
	frappe.response["filename"] = f"{docname}-matrix.xlsx"
	frappe.response["filecontent"] = xlsx_file.getvalue()
	frappe.response["type"] = "binary"


@frappe.whitelist()
def import_matrix_excel(docname=None, file_url=None):
	if not docname:
		frappe.throw(_("Thiếu tham chiếu sổ kế hoạch để nhập dữ liệu."))
	if not file_url:
		frappe.throw(_("Vui lòng chọn tệp Excel để nhập."))

	doc = frappe.get_doc("VNT Financial Plan Book", docname)
	fy_doc, current_year = _get_fiscal_year_info(doc.fiscal_year)
	prev_fy_name, prev_year = _get_previous_fiscal_year(fy_doc)
	prev_book = _find_previous_book(doc, prev_fy_name)

	file_doc = frappe.get_doc("File", {"file_url": file_url})
	file_path = file_doc.get_full_path()

	workbook = load_workbook(file_path, data_only=True)
	plan_sheet = _find_sheet(workbook, ["Ke hoach", "Ke_hoach", "KeHoach"])
	actual_sheet = _find_sheet(workbook, ["Thuc te", "Thuc_te", "ThucTe"])
	if not plan_sheet and not actual_sheet:
		frappe.throw(_("Không tìm thấy sheet \"Ke hoach\" hoặc \"Thuc te\" trong tệp Excel."))

	line_map_current = {line.item_code: line for line in doc.lines if line.item_code}
	line_map_prev = (
		{line.item_code: line for line in prev_book.lines if line.item_code} if prev_book else {}
	)

	entry_cache = {}
	result = {
		"plan_updates": 0,
		"plan_updates_current": 0,
		"plan_updates_prev": 0,
		"actual_updates": 0,
		"annual_updates": 0,
		"annual_updates_current": 0,
		"annual_updates_prev": 0,
		"entries_created": 0,
		"entries_amended": 0,
		"missing_prev_book": 0 if prev_book else 1,
	}

	if plan_sheet:
		result = _import_matrix_sheet(
			plan_sheet,
			doc,
			prev_book,
			current_year,
			prev_year,
			line_map_current,
			line_map_prev,
			entry_cache,
			value_field=None,
			entry_type=_ENTRY_TYPE_ACTUAL,
			allow_annual=True,
			allow_quarters=True,
			result=result,
		)

	if actual_sheet:
		result = _import_matrix_sheet(
			actual_sheet,
			doc,
			prev_book,
			current_year,
			prev_year,
			line_map_current,
			line_map_prev,
			entry_cache,
			value_field="monthly_value",
			entry_type=_ENTRY_TYPE_ACTUAL,
			allow_annual=False,
			allow_quarters=False,
			result=result,
		)

	if result["plan_updates_current"]:
		doc.save()
	if prev_book and result["plan_updates_prev"]:
		prev_book.save()

	for entry in entry_cache.values():
		entry.save()

	return result


def _get_fiscal_year_info(fiscal_year_name):
	fy_doc = frappe.get_doc("Fiscal Year", fiscal_year_name)
	start_date = getdate(fy_doc.year_start_date)
	return fy_doc, start_date.year


def _get_previous_fiscal_year(fy_doc):
	start_date = getdate(fy_doc.year_start_date)
	prev_year = start_date.year - 1
	prev_start = start_date.replace(year=prev_year)
	prev_name = frappe.get_value("Fiscal Year", {"year_start_date": prev_start}, "name")
	if not prev_name:
		prev_name = frappe.get_value("Fiscal Year", {"name": str(prev_year)}, "name")
	return prev_name, prev_year


def _find_previous_book(doc, prev_fiscal_year):
	if not prev_fiscal_year:
		return None
	prev_names = frappe.get_all(
		"VNT Financial Plan Book",
		filters={
			"company": doc.company,
			"template": doc.template,
			"scenario": doc.scenario,
			"fiscal_year": prev_fiscal_year,
		},
		pluck="name",
		order_by="modified desc",
		limit=1,
	)
	if not prev_names:
		return None
	return frappe.get_doc("VNT Financial Plan Book", prev_names[0])


def _get_sorted_lines(doc):
	return sorted(doc.lines, key=lambda row: ((row.sort_order or 0), row.idx))


def _build_plan_quarters(book):
	if not book:
		return {}
	quarters = {}
	for line in book.lines:
		if not line.item_code:
			continue
		plan_12t = line.plan_12t if line.plan_12t is not None else line.annual_plan_value
		quarters[line.item_code] = {
			"3t": line.plan_3t,
			"6t": line.plan_6t,
			"9t": line.plan_9t,
			"12t": plan_12t,
		}
	return quarters


def _get_monthly_item_values(book_name, year, value_field):
	if not book_name:
		return {}

	entries = frappe.get_all(
		"VNT Financial Monthly Entry",
		filters={"book": book_name, "year": year},
		fields=["name", "month", "docstatus", "modified"],
		order_by="month asc, docstatus desc, modified desc",
	)
	selected = {}
	for entry in entries:
		month_key = int(entry.month)
		if month_key not in selected:
			selected[month_key] = entry.name

	values = {}
	for month_key, entry_name in selected.items():
		entry = frappe.get_doc("VNT Financial Monthly Entry", entry_name)
		for line in entry.lines:
			if not line.item_code:
				continue
			item_values = values.setdefault(line.item_code, {})
			item_values[month_key] = line.get(value_field)
	return values


def _build_matrix_headers(prev_year, current_year):
	prev_suffix = str(prev_year)[-2:]
	current_suffix = str(current_year)[-2:]
	headers = [
		"STT",
		"Nhóm",
		"Khoản mục",
		"Mã khoản mục",
		f"KH{prev_year}",
		f"3T.{prev_suffix}",
		f"6T.{prev_suffix}",
		f"9T.{prev_suffix}",
		f"12T.{prev_suffix}",
		f"KH{current_year}",
		f"3T.{current_suffix}",
		f"6T.{current_suffix}",
		f"9T.{current_suffix}",
		f"12T.{current_suffix}",
	]
	for month in range(1, 13):
		headers.append(f"T{month:02d}.{prev_suffix}")
	for month in range(1, 13):
		headers.append(f"T{month:02d}.{current_suffix}")
	headers.append("Lũy kế")
	return headers


def _build_matrix_column_widths(total_columns):
	widths = [5, 22, 30, 0, 14, 12, 12, 12, 12, 14, 12, 12, 12, 12]
	remaining = total_columns - len(widths)
	if remaining > 0:
		widths.extend([10] * remaining)
	return widths


def _build_matrix_workbook(headers, plan_rows, actual_rows, column_widths):
	

	wb = Workbook(write_only=True)
	if wb.sheetnames:
		wb.remove(wb[wb.sheetnames[0]])

	_write_matrix_sheet(wb, "Ke hoach", headers, plan_rows, column_widths, WriteOnlyCell, Font, get_column_letter)
	_write_matrix_sheet(wb, "Thuc te", headers, actual_rows, column_widths, WriteOnlyCell, Font, get_column_letter)

	xlsx_file = BytesIO()
	wb.save(xlsx_file)
	return xlsx_file


def _write_matrix_sheet(
	workbook,
	title,
	headers,
	rows,
	column_widths,
	WriteOnlyCell,
	Font,
	get_column_letter,
):
	ws = workbook.create_sheet(title)
	for idx, width in enumerate(column_widths):
		if width:
			ws.column_dimensions[get_column_letter(idx + 1)].width = width

	header_cells = []
	for value in headers:
		cell = WriteOnlyCell(ws, value=value)
		cell.font = Font(bold=True)
		header_cells.append(cell)
	ws.append(header_cells)

	for row in rows:
		ws.append(row)


def _build_matrix_rows(
	lines,
	annual_prev,
	annual_current,
	values_prev,
	values_current,
	prev_year,
	current_year,
	quarter_prev=None,
	quarter_current=None,
	use_formulas=False,
):
	rows = []
	prev_month_start = 15
	prev_month_end = 26
	current_month_start = 27
	current_month_end = 38
	for idx, line in enumerate(lines, start=1):
		excel_row = 2 + len(rows)
		is_group = line.row_kind == _ROW_KIND_GROUP
		row = [
			"" if is_group else idx,
			line.group_name or "",
			line.item_name or "",
			line.item_code or "",
		]

		if is_group:
			numeric_columns = 10 + 12 + 12 + 1
			row.extend([None] * numeric_columns)
			rows.append(row)
			continue

		item_prev_months = values_prev.get(line.item_code, {})
		item_current_months = values_current.get(line.item_code, {})
		item_prev_quarters = (quarter_prev or {}).get(line.item_code, {})
		item_current_quarters = (quarter_current or {}).get(line.item_code, {})

		prev_annual = annual_prev.get(line.item_code)
		current_annual = annual_current.get(line.item_code)

		if use_formulas:
			prev_3t = _sum_formula(excel_row, prev_month_start, prev_month_start + 2)
			prev_6t = _sum_formula(excel_row, prev_month_start, prev_month_start + 5)
			prev_9t = _sum_formula(excel_row, prev_month_start, prev_month_start + 8)
			prev_12t = _sum_formula(excel_row, prev_month_start, prev_month_end)

			current_3t = _sum_formula(excel_row, current_month_start, current_month_start + 2)
			current_6t = _sum_formula(excel_row, current_month_start, current_month_start + 5)
			current_9t = _sum_formula(excel_row, current_month_start, current_month_start + 8)
			current_12t = _sum_formula(excel_row, current_month_start, current_month_end)
		else:
			if item_prev_quarters:
				prev_3t = item_prev_quarters.get("3t")
				prev_6t = item_prev_quarters.get("6t")
				prev_9t = item_prev_quarters.get("9t")
				prev_12t = item_prev_quarters.get("12t")
			else:
				prev_3t = _sum_months(item_prev_months, range(1, 4))
				prev_6t = _sum_months(item_prev_months, range(1, 7))
				prev_9t = _sum_months(item_prev_months, range(1, 10))
				prev_12t = _sum_months(item_prev_months, range(1, 13))

			if item_current_quarters:
				current_3t = item_current_quarters.get("3t")
				current_6t = item_current_quarters.get("6t")
				current_9t = item_current_quarters.get("9t")
				current_12t = item_current_quarters.get("12t")
			else:
				current_3t = _sum_months(item_current_months, range(1, 4))
				current_6t = _sum_months(item_current_months, range(1, 7))
				current_9t = _sum_months(item_current_months, range(1, 10))
				current_12t = _sum_months(item_current_months, range(1, 13))

		row.extend(
			[
				prev_annual,
				prev_3t,
				prev_6t,
				prev_9t,
				prev_12t,
				current_annual,
				current_3t,
				current_6t,
				current_9t,
				current_12t,
			]
		)

		for month in range(1, 13):
			row.append(item_prev_months.get(month))
		for month in range(1, 13):
			row.append(item_current_months.get(month))

		if use_formulas:
			row.append(_sum_formula(excel_row, current_month_start, current_month_end))
		else:
			row.append(current_12t)
		rows.append(row)
	return rows


def _sum_months(values, months):
	total = 0
	has_value = False
	for month in months:
		value = values.get(month)
		if value is None:
			continue
		total += flt(value)
		has_value = True
	return total if has_value else None


def _sum_formula(row, start_col, end_col):
	start_letter = _excel_column_letter(start_col)
	end_letter = _excel_column_letter(end_col)
	return f"=SUM({start_letter}{row}:{end_letter}{row})"


def _excel_column_letter(index):
	letter = ""
	while index:
		index, remainder = divmod(index - 1, 26)
		letter = chr(65 + remainder) + letter
	return letter


def _find_sheet(workbook, candidates):
	for name in workbook.sheetnames:
		for candidate in candidates:
			if name.strip().lower() == candidate.strip().lower():
				return workbook[name]
	return None


def _import_matrix_sheet(
	sheet,
	current_book,
	prev_book,
	current_year,
	prev_year,
	line_map_current,
	line_map_prev,
	entry_cache,
	value_field,
	entry_type,
	allow_annual,
	allow_quarters,
	result,
):
	header = [cell.value for cell in next(sheet.iter_rows(min_row=1, max_row=1))]
	header_map = _parse_matrix_header(header)
	if header_map["item_code"] is None:
		frappe.throw(_("Thiếu cột \"Mã khoản mục\" trong file Excel."))

	for row in sheet.iter_rows(min_row=2, values_only=True):
		if not row or all(cell is None for cell in row):
			continue

		item_code = _safe_text(_cell(row, header_map["item_code"]))
		if not item_code:
			continue

		line_current = line_map_current.get(item_code)
		line_prev = line_map_prev.get(item_code)

		if allow_annual:
			for year, col_idx in header_map["annual"].items():
				value = _parse_number(_cell(row, col_idx))
				if value is None:
					continue
				if year == current_year and line_current:
					line_current.annual_plan_value = value
					result["annual_updates"] += 1
					result["annual_updates_current"] += 1
					result["plan_updates"] += 1
					result["plan_updates_current"] += 1
				elif year == prev_year and line_prev:
					line_prev.annual_plan_value = value
					result["annual_updates"] += 1
					result["annual_updates_prev"] += 1
					result["plan_updates"] += 1
					result["plan_updates_prev"] += 1

		if allow_quarters:
			for year, quarter_map in header_map["quarters"].items():
				if year == current_year:
					target_line = line_current
				elif year == prev_year:
					target_line = line_prev
				else:
					target_line = None

				if not target_line:
					continue

				plan_3t = _parse_number(_cell(row, quarter_map.get("3t")))
				plan_6t = _parse_number(_cell(row, quarter_map.get("6t")))
				plan_9t = _parse_number(_cell(row, quarter_map.get("9t")))
				plan_12t = _parse_number(_cell(row, quarter_map.get("12t")))
				if any(value is not None for value in (plan_3t, plan_6t, plan_9t, plan_12t)):
					result["plan_updates"] += 1
					if year == current_year:
						result["plan_updates_current"] += 1
					elif year == prev_year:
						result["plan_updates_prev"] += 1
				target_line.plan_3t = plan_3t
				target_line.plan_6t = plan_6t
				target_line.plan_9t = plan_9t
				target_line.plan_12t = plan_12t

		if not value_field:
			continue

		for year, month_map in header_map["months"].items():
			target_book = None
			target_line = None
			if year == current_year:
				target_book = current_book
				target_line = line_current
			elif year == prev_year and prev_book:
				target_book = prev_book
				target_line = line_prev
			else:
				continue

			for month, col_idx in month_map.items():
				value = _parse_number(_cell(row, col_idx))
				if value is None or not target_line:
					continue
				entry = _get_or_create_monthly_entry(
					entry_cache,
					target_book,
					year,
					month,
					entry_type,
					result,
				)
				line = _get_or_create_entry_line(entry, target_line)
				line.set(value_field, value)
				result["actual_updates"] += 1

	return result


def _parse_matrix_header(headers):
	mapping = {"item_code": None, "annual": {}, "quarters": {}, "months": {}}
	for idx, header in enumerate(headers or []):
		label = (header or "").strip()
		if not label:
			continue
		label_key = _normalize_header(label)
		if label_key in {"ma khoan muc"}:
			mapping["item_code"] = idx
			continue
		if label.startswith("KH") and label[2:].isdigit():
			mapping["annual"][int(label[2:])] = idx
			continue

		match = re.match(r"^(3T|6T|9T|12T)\\.(\\d{2}|\\d{4})$", label)
		if match:
			quarter = match.group(1).lower()
			year = int(match.group(2))
			if year < 100:
				year += 2000
			mapping.setdefault("quarters", {}).setdefault(year, {})[quarter] = idx
			continue

		match = re.match(r"^T(\\d{2})\\.(\\d{2}|\\d{4})$", label)
		if match:
			month = int(match.group(1))
			year = int(match.group(2))
			if year < 100:
				year += 2000
			mapping.setdefault("months", {}).setdefault(year, {})[month] = idx
	return mapping


def _get_or_create_monthly_entry(entry_cache, book, year, month, entry_type, result):
	key = (book.name, year, month)
	if key in entry_cache:
		return entry_cache[key]

	month_str = f"{month:02d}"
	entries = frappe.get_all(
		"VNT Financial Monthly Entry",
		filters={"book": book.name, "year": year, "month": month_str},
		fields=["name", "docstatus", "modified"],
		order_by="docstatus desc, modified desc",
		limit=1,
	)
	if entries:
		entry = frappe.get_doc("VNT Financial Monthly Entry", entries[0].name)
		if entry.docstatus == 1:
			entry = frappe.copy_doc(entry)
			entry.amended_from = entries[0].name
			entry.docstatus = 0
			result["entries_amended"] += 1
	else:
		entry = frappe.get_doc(
			{
				"doctype": "VNT Financial Monthly Entry",
				"company": book.company,
				"fiscal_year": book.fiscal_year,
				"book": book.name,
				"month": month_str,
				"year": year,
				"entry_type": _ENTRY_TYPE_ACTUAL,
			}
		)
		result["entries_created"] += 1

	if not entry.entry_type:
		entry.entry_type = _ENTRY_TYPE_ACTUAL

	entry_cache[key] = entry
	return entry


def _get_or_create_entry_line(entry, book_line):
	for line in entry.lines:
		if line.item_code == book_line.item_code:
			return line

	line = entry.append("lines", {})
	line.item_code = book_line.item_code
	line.item_name = book_line.item_name
	line.group_name = book_line.group_name
	line.row_kind = book_line.row_kind
	line.item_type = book_line.item_type
	line.sort_order = book_line.sort_order
	return line


def _parse_number(value):
	if value is None or value == "":
		return None
	if isinstance(value, str):
		text = value.strip()
		if not text:
			return None
		if text.startswith("(") and text.endswith(")"):
			text = "-" + text[1:-1]
		text = text.replace(",", "")
		try:
			return flt(text)
		except ValueError:
			return None
	return flt(value)


def _safe_text(value):
	if value is None:
		return None
	return str(value).strip()


def _build_line_key(doi_tuong, ct_doi_tuong, chi_tiet_doi_tuong_c2, khoan_muc, ct):
	parts = [
		doi_tuong or "",
		ct_doi_tuong or "",
		chi_tiet_doi_tuong_c2 or "",
		khoan_muc or "",
		ct or "",
	]
	return "||".join(str(part).strip() for part in parts)


_ROW_KIND_GROUP = "Tiêu đề nhóm"
_ENTRY_TYPE_ACTUAL = "Thực tế"
