# Copyright (c) 2026, vinatex and contributors
# For license information, please see license.txt

import json
import re
import unicodedata
from io import BytesIO

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file
from openpyxl import Workbook
from openpyxl.styles import Font


class VNTFinancialActualSummary(Document):
	def validate(self):
		_apply_profit_lines(self.lines)


@frappe.whitelist()
def get_previous_actual_summary_values(company=None, template=None, fiscal_year=None, plan_book=None):
	if not (company and template and fiscal_year):
		frappe.throw(_("Thiếu thông tin để lấy dữ liệu năm trước."))

	fy_doc = frappe.get_doc("Fiscal Year", fiscal_year)
	prev_fy_name, _ = _get_previous_fiscal_year(fy_doc)
	if not prev_fy_name:
		return {"lines": []}

	filters = {
		"company": company,
		"template": template,
		"fiscal_year": prev_fy_name,
	}
	if plan_book:
		filters["plan_book"] = plan_book

	prev_name = frappe.get_value(
		"VNT Financial Actual Summary",
		filters,
		"name",
		order_by="modified desc",
	)
	if not prev_name:
		return {"lines": []}

	doc = frappe.get_doc("VNT Financial Actual Summary", prev_name)
	lines = []
	for line in doc.lines:
		lines.append(
			{
				"nhom_to": line.nhom_to,
				"item_code": line.item_code,
				"doi_tuong": line.doi_tuong,
				"ct_doi_tuong": line.ct_doi_tuong,
				"chi_tiet_doi_tuong_c2": line.chi_tiet_doi_tuong_c2,
				"khoan_muc": line.khoan_muc,
				"ct": line.ct,
				"current_plan": line.current_plan,
				"current_3t": line.current_3t,
				"current_6t": line.current_6t,
				"current_9t": line.current_9t,
				"current_12t": line.current_12t,
				"current_t01": line.current_t01,
				"current_t02": line.current_t02,
				"current_t03": line.current_t03,
				"current_t04": line.current_t04,
				"current_t05": line.current_t05,
				"current_t06": line.current_t06,
				"current_t07": line.current_t07,
				"current_t08": line.current_t08,
				"current_t09": line.current_t09,
				"current_t10": line.current_t10,
				"current_t11": line.current_t11,
				"current_t12": line.current_t12,
			}
		)
	return {"lines": lines, "source": prev_name, "prev_fiscal_year": prev_fy_name}


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
		group_label = _extract_group_label(field.label)
		for row in doc.get(field.fieldname) or []:
			items.append(
				{
					"nhom_to": row.nhom_to or group_label,
					"doi_tuong": row.doi_tuong,
					"ct_doi_tuong": row.ct_doi_tuong,
					"chi_tiet_doi_tuong_c2": row.chi_tiet_doi_tuong_c2,
					"khoan_muc": row.khoan_muc,
					"ct": row.ct,
					"item_code": row.get("item_code"),
				}
			)
	return items


@frappe.whitelist()
def download_actual_summary_excel(docname=None):
	if not docname:
		frappe.throw(_("Thiếu tham chiếu bảng tổng hợp để tải xuống."))

	doc = frappe.get_doc("VNT Financial Actual Summary", docname)
	if not doc.fiscal_year:
		frappe.throw(_("Vui lòng chọn Năm tài chính để tải dữ liệu."))

	fy_doc, current_year = _get_fiscal_year_info(doc.fiscal_year)
	_, prev_year = _get_previous_fiscal_year(fy_doc)
	headers = _build_matrix_headers(prev_year, current_year)
	rows, parent_group_values, group_values = _build_summary_rows(doc.lines or [])
	xlsx_file = _build_summary_workbook(headers, rows, parent_group_values, group_values)
	frappe.response["filename"] = f"Thuc-te-{docname}.xlsx"
	frappe.response["filecontent"] = xlsx_file.getvalue()
	frappe.response["type"] = "binary"


@frappe.whitelist()
def save_actual_summary_lines(docname=None, lines=None):
	if not docname:
		frappe.throw(_("Thiếu tham chiếu bảng tổng hợp để lưu."))
	if lines is None:
		frappe.throw(_("Thiếu dữ liệu để lưu."))

	if isinstance(lines, str):
		lines = json.loads(lines)

	doc = frappe.get_doc("VNT Financial Actual Summary", docname)
	line_map = {line.name: line for line in doc.lines}
	for payload in lines:
		row_name = payload.get("name")
		if not row_name:
			continue
		line = line_map.get(row_name)
		if not line:
			continue
		for field in _NUMERIC_FIELDS:
			if field in payload:
				line.set(field, _to_number(payload.get(field)))

	_apply_profit_lines(doc.lines)
	doc.save()
	return {"updated": len(lines)}


@frappe.whitelist()
def import_actual_summary_excel(docname=None, file_url=None):
	if not docname:
		frappe.throw(_("Thiếu tham chiếu bảng tổng hợp để nhập dữ liệu."))
	if not file_url:
		frappe.throw(_("Vui lòng chọn tệp Excel để nhập."))

	doc = frappe.get_doc("VNT Financial Actual Summary", docname)
	if not doc.fiscal_year:
		frappe.throw(_("Vui lòng chọn Năm tài chính trước khi nhập."))

	fy_doc, current_year = _get_fiscal_year_info(doc.fiscal_year)
	_, prev_year = _get_previous_fiscal_year(fy_doc)

	rows = read_xlsx_file_from_attached_file(file_url=file_url)
	if not rows:
		frappe.throw(_("Không tìm thấy dữ liệu trong tệp Excel."))

	header_map = _build_header_map(rows[0], prev_year, current_year)
	if header_map.get("item_code") is None:
		frappe.throw(_("Thiếu cột \"Mã khoản mục\" trong tệp Excel."))

	base_lines = list(doc.lines or [])
	if not base_lines and doc.template:
		doc.set("lines", [])
		for item in get_template_items(doc.template):
			doc.append("lines", item)
		base_lines = list(doc.lines or [])

	lines_by_code = {line.item_code: line for line in base_lines if line.item_code}
	for row_index, row in enumerate(rows[1:]):
		if not row or all(cell is None for cell in row):
			continue

		item_code = _safe_text(_cell(row, header_map.get("item_code")))
		stt_value = _coerce_int(_cell(row, header_map.get("stt")))
		line = _resolve_line(doc, base_lines, lines_by_code, item_code, stt_value, row_index)

		if item_code:
			line.item_code = item_code
			lines_by_code[item_code] = line
		if stt_value is not None:
			line.stt = stt_value

		_assign_text_field(line, "nhom_to", row, header_map, "nhom_to")
		_assign_text_field(line, "doi_tuong", row, header_map, "doi_tuong")
		_assign_text_field(line, "ct_doi_tuong", row, header_map, "ct_doi_tuong")
		_assign_text_field(line, "chi_tiet_doi_tuong_c2", row, header_map, "chi_tiet_doi_tuong_c2")
		_assign_text_field(line, "khoan_muc", row, header_map, "khoan_muc")
		_assign_text_field(line, "ct", row, header_map, "ct")

		_assign_number_field(line, "prev_plan", row, header_map, "prev_plan")
		_assign_number_field(line, "prev_3t", row, header_map, "prev_3t")
		_assign_number_field(line, "prev_6t", row, header_map, "prev_6t")
		_assign_number_field(line, "prev_9t", row, header_map, "prev_9t")
		_assign_number_field(line, "prev_12t", row, header_map, "prev_12t")

		_assign_number_field(line, "current_plan", row, header_map, "current_plan")
		_assign_number_field(line, "current_3t", row, header_map, "current_3t")
		_assign_number_field(line, "current_6t", row, header_map, "current_6t")
		_assign_number_field(line, "current_9t", row, header_map, "current_9t")
		_assign_number_field(line, "current_12t", row, header_map, "current_12t")

		_assign_number_field(line, "prev_t01", row, header_map, "prev_t01")
		_assign_number_field(line, "prev_t02", row, header_map, "prev_t02")
		_assign_number_field(line, "prev_t03", row, header_map, "prev_t03")
		_assign_number_field(line, "prev_t04", row, header_map, "prev_t04")
		_assign_number_field(line, "prev_t05", row, header_map, "prev_t05")
		_assign_number_field(line, "prev_t06", row, header_map, "prev_t06")
		_assign_number_field(line, "prev_t07", row, header_map, "prev_t07")
		_assign_number_field(line, "prev_t08", row, header_map, "prev_t08")
		_assign_number_field(line, "prev_t09", row, header_map, "prev_t09")
		_assign_number_field(line, "prev_t10", row, header_map, "prev_t10")
		_assign_number_field(line, "prev_t11", row, header_map, "prev_t11")
		_assign_number_field(line, "prev_t12", row, header_map, "prev_t12")

		_assign_number_field(line, "current_t01", row, header_map, "current_t01")
		_assign_number_field(line, "current_t02", row, header_map, "current_t02")
		_assign_number_field(line, "current_t03", row, header_map, "current_t03")
		_assign_number_field(line, "current_t04", row, header_map, "current_t04")
		_assign_number_field(line, "current_t05", row, header_map, "current_t05")
		_assign_number_field(line, "current_t06", row, header_map, "current_t06")
		_assign_number_field(line, "current_t07", row, header_map, "current_t07")
		_assign_number_field(line, "current_t08", row, header_map, "current_t08")
		_assign_number_field(line, "current_t09", row, header_map, "current_t09")
		_assign_number_field(line, "current_t10", row, header_map, "current_t10")
		_assign_number_field(line, "current_t11", row, header_map, "current_t11")
		_assign_number_field(line, "current_t12", row, header_map, "current_t12")

		_assign_number_field(line, "luy_ke", row, header_map, "luy_ke")
		_apply_quarter_months(line, "prev")
		_apply_quarter_months(line, "current")

	doc.save()
	return {"updated": len(doc.lines)}


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


def _extract_group_label(label):
	if not label:
		return None
	match = re.search(r"Nhóm\s*\d+", label, flags=re.IGNORECASE)
	if match:
		return match.group(0)
	return label


def _build_matrix_headers(prev_year, current_year):
	prev_suffix = str(prev_year)[-2:]
	current_suffix = str(current_year)[-2:]
	headers = [
		"Nhóm to",
		"Nhóm",
		"Chi tiết đối tượng",
		"Chi tiết đối tượng cấp 2",
		"Khoản mục",
		"Chi tiết khoản mục",
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


def _build_header_map(headers, prev_year, current_year):
	prev_suffix = str(prev_year)[-2:]
	current_suffix = str(current_year)[-2:]
	expected = {
		_normalize_header("Nhóm to"): "nhom_to",
		_normalize_header("Nhóm"): "doi_tuong",
		_normalize_header("Chi tiết đối tượng"): "ct_doi_tuong",
		_normalize_header("Chi tiết đối tượng cấp 2"): "chi_tiet_doi_tuong_c2",
		_normalize_header("Khoản mục"): "khoan_muc",
		_normalize_header("Chi tiết khoản mục"): "ct",
		_normalize_header("Mã khoản mục"): "item_code",
		_normalize_header(f"KH{prev_year}"): "prev_plan",
		_normalize_header(f"3T.{prev_suffix}"): "prev_3t",
		_normalize_header(f"6T.{prev_suffix}"): "prev_6t",
		_normalize_header(f"9T.{prev_suffix}"): "prev_9t",
		_normalize_header(f"12T.{prev_suffix}"): "prev_12t",
		_normalize_header(f"KH{current_year}"): "current_plan",
		_normalize_header(f"3T.{current_suffix}"): "current_3t",
		_normalize_header(f"6T.{current_suffix}"): "current_6t",
		_normalize_header(f"9T.{current_suffix}"): "current_9t",
		_normalize_header(f"12T.{current_suffix}"): "current_12t",
		_normalize_header("Lũy kế"): "luy_ke",
	}
	expected[_normalize_header("Nhóm lớn")] = "nhom_to"
	expected[_normalize_header("Đối tượng")] = "doi_tuong"
	expected[_normalize_header("Chi tiết đối tượng c2")] = "chi_tiet_doi_tuong_c2"
	expected[_normalize_header("Chi tiết đối tượng cấp2")] = "chi_tiet_doi_tuong_c2"
	for month in range(1, 13):
		expected[_normalize_header(f"T{month:02d}.{prev_suffix}")] = f"prev_t{month:02d}"
		expected[_normalize_header(f"T{month:02d}.{current_suffix}")] = f"current_t{month:02d}"

	mapping = {}
	for idx, header in enumerate(headers or []):
		key = _normalize_header(header)
		fieldname = expected.get(key)
		if fieldname:
			mapping[fieldname] = idx
	return mapping


def _normalize_header(value):
	text = (value or "").strip().lower()
	text = unicodedata.normalize("NFKD", text)
	text = "".join(char for char in text if not unicodedata.combining(char))
	return re.sub(r"\s+", " ", text)


def _cell(row, index):
	if index is None:
		return None
	if index >= len(row):
		return None
	return row[index]


def _safe_text(value):
	if value is None:
		return None
	return str(value).strip()


NUMBER_PRECISION = 6


def _normalize_numeric_text(value):
	text = (value or "").strip()
	if not text:
		return ""
	if text.startswith("(") and text.endswith(")"):
		text = f"-{text[1:-1]}"
	text = text.replace("\u00a0", "").replace(" ", "")
	text = re.sub(r"[^0-9,.\-]", "", text)
	if text in {"", "-", ".", ",", "-.", "-,"}:
		return ""
	sign = "-" if text.startswith("-") else ""
	text = text.lstrip("-").replace("-", "")
	has_dot = "." in text
	has_comma = "," in text
	decimal_sep = None
	if has_dot and has_comma:
		decimal_sep = "." if text.rfind(".") > text.rfind(",") else ","
	elif has_comma:
		parts = text.split(",")
		decimal_sep = "," if len(parts[-1]) != 3 else None
	elif has_dot:
		parts = text.split(".")
		decimal_sep = "." if len(parts[-1]) != 3 else None

	if decimal_sep:
		parts = text.split(decimal_sep)
		int_part = re.sub(r"[.,]", "", parts[0])
		frac_part = re.sub(r"[.,]", "", "".join(parts[1:]))
		normalized = int_part if int_part else "0"
		if frac_part:
			normalized = f"{normalized}.{frac_part}"
	else:
		normalized = re.sub(r"[.,]", "", text)

	return f"{sign}{normalized}" if normalized else ""


def _to_precision(value):
	return flt(value, precision=NUMBER_PRECISION)


def _to_number(value):
	if value in (None, ""):
		return None
	if isinstance(value, str):
		value = _normalize_numeric_text(value)
		if value == "":
			return None
	try:
		return _to_precision(value)
	except (TypeError, ValueError):
		return None


def _coerce_int(value):
	try:
		return cint(value)
	except (TypeError, ValueError):
		return None


def _assign_text_field(line, fieldname, row, header_map, key):
	index = header_map.get(key)
	if index is None:
		return
	value = _safe_text(_cell(row, index))
	if value in (None, ""):
		return
	setattr(line, fieldname, value)


def _assign_number_field(line, fieldname, row, header_map, key):
	index = header_map.get(key)
	if index is None:
		return
	setattr(line, fieldname, _to_number(_cell(row, index)))


def _resolve_line(doc, base_lines, lines_by_code, item_code, stt_value, row_index):
	if item_code and item_code in lines_by_code:
		return lines_by_code[item_code]
	if stt_value and 1 <= stt_value <= len(base_lines):
		return base_lines[stt_value - 1]
	if row_index < len(base_lines):
		return base_lines[row_index]
	line = doc.append("lines", {})
	base_lines.append(line)
	if item_code:
		lines_by_code[item_code] = line
	return line


def _apply_quarter_months(line, prefix):
	month_fields = {month: f"{prefix}_t{month:02d}" for month in range(1, 13)}
	quarter_fields = {
		3: f"{prefix}_3t",
		6: f"{prefix}_6t",
		9: f"{prefix}_9t",
		12: f"{prefix}_12t",
	}
	months = {month: getattr(line, field) for month, field in month_fields.items()}
	for end_month, quarter_field in quarter_fields.items():
		quarter_value = getattr(line, quarter_field)
		if quarter_value in (None, ""):
			continue
		if months.get(end_month) not in (None, ""):
			continue
		total = 0
		for month in range(1, end_month):
			value = months.get(month)
			if value in (None, ""):
				continue
			total += _to_precision(value)
		months[end_month] = _to_precision(quarter_value) - total

	for month, field in month_fields.items():
		if getattr(line, field) in (None, "") and months.get(month) is not None:
			setattr(line, field, months[month])


_NUMERIC_FIELDS = [
	"prev_plan",
	"prev_3t",
	"prev_6t",
	"prev_9t",
	"prev_12t",
	"current_plan",
	"current_3t",
	"current_6t",
	"current_9t",
	"current_12t",
] + [f"prev_t{month:02d}" for month in range(1, 13)] + [
	f"current_t{month:02d}" for month in range(1, 13)
] + [
	"luy_ke",
]


def _normalize_value(value):
	text = (value or "").strip().lower()
	text = unicodedata.normalize("NFKD", text)
	text = "".join(char for char in text if not unicodedata.combining(char))
	return re.sub(r"\s+", " ", text)


def _apply_profit_lines(lines):
	if not lines:
		return
	totals = {}
	for line in lines:
		group = _safe_text(getattr(line, "doi_tuong", None))
		if not group:
			continue
		kind = _normalize_value(getattr(line, "khoan_muc", None))
		if kind not in {"doanh thu", "chi phi"}:
			continue
		group_totals = totals.setdefault(group, {"doanh thu": {}, "chi phi": {}})
		target = group_totals[kind]
		for field in _NUMERIC_FIELDS:
			value = getattr(line, field, None)
			if value in (None, ""):
				continue
			target[field] = (target.get(field) or 0) + _to_precision(value)

	for line in lines:
		if _normalize_value(getattr(line, "khoan_muc", None)) != "loi nhuan":
			continue
		group = _safe_text(getattr(line, "doi_tuong", None))
		if not group:
			continue
		group_totals = totals.get(group, {})
		revenue = group_totals.get("doanh thu", {})
		cost = group_totals.get("chi phi", {})
		for field in _NUMERIC_FIELDS:
			rev_value = revenue.get(field)
			cost_value = cost.get(field)
			if rev_value is None and cost_value is None:
				continue
			setattr(line, field, _to_precision(rev_value or 0) - _to_precision(cost_value or 0))


def _build_summary_rows(lines):
	rows = []
	parent_group_values = []
	group_values = []
	for idx, line in enumerate(lines, start=1):
		parent_group_values.append(_safe_text(getattr(line, "nhom_to", None)) or "")
		group_values.append(_safe_text(getattr(line, "doi_tuong", None)) or "")
		rows.append(
			[
				line.nhom_to,
				line.doi_tuong,
				line.ct_doi_tuong,
				line.chi_tiet_doi_tuong_c2,
				line.khoan_muc,
				line.ct,
				line.item_code,
				_export_value(line.prev_plan),
				_export_value(line.prev_3t),
				_export_value(line.prev_6t),
				_export_value(line.prev_9t),
				_export_value(line.prev_12t),
				_export_value(line.current_plan),
				_export_value(line.current_3t),
				_export_value(line.current_6t),
				_export_value(line.current_9t),
				_export_value(line.current_12t),
				_export_value(line.prev_t01),
				_export_value(line.prev_t02),
				_export_value(line.prev_t03),
				_export_value(line.prev_t04),
				_export_value(line.prev_t05),
				_export_value(line.prev_t06),
				_export_value(line.prev_t07),
				_export_value(line.prev_t08),
				_export_value(line.prev_t09),
				_export_value(line.prev_t10),
				_export_value(line.prev_t11),
				_export_value(line.prev_t12),
				_export_value(line.current_t01),
				_export_value(line.current_t02),
				_export_value(line.current_t03),
				_export_value(line.current_t04),
				_export_value(line.current_t05),
				_export_value(line.current_t06),
				_export_value(line.current_t07),
				_export_value(line.current_t08),
				_export_value(line.current_t09),
				_export_value(line.current_t10),
				_export_value(line.current_t11),
				_export_value(line.current_t12),
				_export_value(line.luy_ke),
			]
		)
	return rows, parent_group_values, group_values




def _build_summary_workbook(headers, rows, parent_group_values, group_values):
	wb = Workbook()
	ws = wb.active
	ws.title = "Tong hop"
	ws.append(headers)
	header_font = Font(bold=True)
	for col in range(1, len(headers) + 1):
		ws.cell(row=1, column=col).font = header_font

	for row in rows:
		ws.append(row)

	_merge_group_cells(ws, 2, parent_group_values, 1)
	_merge_group_cells(ws, 2, group_values, 2)

	xlsx_file = BytesIO()
	wb.save(xlsx_file)
	return xlsx_file


def _merge_group_cells(ws, start_row, group_values, column_index):
	if not group_values:
		return
	group_start = 0
	current_value = group_values[0]
	for idx in range(1, len(group_values) + 1):
		next_value = group_values[idx] if idx < len(group_values) else None
		if next_value != current_value:
			if current_value and idx - group_start > 1:
				ws.merge_cells(
					start_row=start_row + group_start,
					start_column=column_index,
					end_row=start_row + idx - 1,
					end_column=column_index,
				)
			group_start = idx
			current_value = next_value


def _export_value(value):
	if value in (None, ""):
		return None
	if _to_precision(value) == 0:
		return None
	return value
