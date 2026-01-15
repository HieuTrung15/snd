# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import json
import unicodedata

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from frappe.utils.xlsxutils import make_xlsx
from frappe.utils import flt
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

class VNTFinancialMonthlyEntry(Document):
	def validate(self):
		if self.amended_from:
			return
		if not (self.month and self.fiscal_year):
			return
		filters = {
			"month": self.month,
			"fiscal_year": self.fiscal_year,
			"name": ["!=", self.name],
			"docstatus": ["<", 2],
		}
		if self.book:
			filters["book"] = self.book
		else:
			if not self.template:
				return
			filters["template"] = self.template
		exists = frappe.db.exists("VNT Financial Monthly Entry", filters)
		if exists:
			frappe.throw(_("Đã tồn tại phiếu tháng cho dữ liệu đã chọn."))


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
def get_grouped_entry_data(docname=None):
	if not docname:
		frappe.throw(_("Thiếu phiếu tháng để tải dữ liệu."))

	doc = frappe.get_doc("VNT Financial Monthly Entry", docname)
	if not doc.template:
		frappe.throw(_("Phiếu tháng chưa có Mẫu báo cáo."))

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
		value_map[key] = line.gia_tri

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
			items.append(
				{
					"doi_tuong": row.doi_tuong,
					"ct_doi_tuong": row.ct_doi_tuong,
					"chi_tiet_doi_tuong_c2": row.chi_tiet_doi_tuong_c2,
					"khoan_muc": row.khoan_muc,
					"ct": row.ct,
					"gia_tri": value_map.get(key),
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
			"book": doc.book,
			"month": doc.month,
			"docstatus": doc.docstatus,
		},
		"groups": groups,
	}


@frappe.whitelist()
def create_monthly_entry(book=None, template=None, company=None, fiscal_year=None, month=None):
	if book:
		book_doc = frappe.get_doc("VNT Financial Plan Book", book)
		company = book_doc.company
		fiscal_year = book_doc.fiscal_year
		template = book_doc.template

	if not (company and fiscal_year and template and month):
		frappe.throw(_("Thiếu thông tin để tạo phiếu tháng."))

	template_doc = frappe.get_doc("VNT Financial Report Template", template)

	doc = frappe.new_doc("VNT Financial Monthly Entry")
	doc.company = company
	doc.fiscal_year = fiscal_year
	doc.template = template
	doc.book = book
	doc.month = month
	doc.entry_type = "Thực tế"

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
					"gia_tri": None,
				}
			)
	doc.set("lines", lines)
	doc.insert()
	return {"name": doc.name}


@frappe.whitelist()
def delete_monthly_entry(docname=None):
	if not docname:
		frappe.throw(_("Thiếu phiếu tháng để xóa."))

	doc = frappe.get_doc("VNT Financial Monthly Entry", docname)
	if doc.docstatus == 1:
		frappe.throw(_("Phiếu đã ghi nhận, không thể xóa."))

	doc.delete()
	return {"deleted": docname}


@frappe.whitelist()
def save_grouped_entry(docname=None, lines=None):
	if not docname:
		frappe.throw(_("Thiếu phiếu tháng để lưu dữ liệu."))
	if lines is None:
		frappe.throw(_("Thiếu dữ liệu để lưu."))

	if isinstance(lines, str):
		lines = json.loads(lines)

	doc = frappe.get_doc("VNT Financial Monthly Entry", docname)
	if doc.docstatus == 1:
		frappe.throw(_("Phiếu đã ghi nhận, vui lòng tạo điều chỉnh để cập nhật."))

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
				"gia_tri": flt(line.get("gia_tri")) if line.get("gia_tri") not in (None, "") else None,
			},
		)
	doc.save()
	return {"name": doc.name}


@frappe.whitelist()
def download_monthly_entry_excel(docname=None):
	if not docname:
		frappe.throw(_("Thiếu tham chiếu phiếu tháng để tải xuống."))

	doc = frappe.get_doc("VNT Financial Monthly Entry", docname)
	headers = [
		"Mã khoản mục",
		"Tên khoản mục",
		"Nhóm",
		"Loại dòng",
		"Loại khoản mục",
		"Giá trị tháng",
		"Nguồn dữ liệu",
		"Chi tiết dữ liệu",
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
				line.monthly_value,
				line.data_source,
				line.data_detail,
				line.sort_order,
				line.note,
			]
		)



	xlsx_file = make_xlsx(data, "Nhap thang")
	frappe.response["filename"] = f"{docname}.xlsx"
	frappe.response["filecontent"] = xlsx_file.getvalue()
	frappe.response["type"] = "binary"


@frappe.whitelist()
def import_monthly_entry_excel(docname=None, file_url=None):
	if not docname:
		frappe.throw(_("Thiếu tham chiếu phiếu tháng để nhập dữ liệu."))
	if not file_url:
		frappe.throw(_("Vui lòng chọn tệp Excel để nhập."))

	doc = frappe.get_doc("VNT Financial Monthly Entry", docname)

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
		monthly_value = _cell(row, header_map.get("monthly_value"))
		line.monthly_value = flt(monthly_value) if monthly_value not in (None, "") else None
		line.data_source = _cell(row, header_map.get("data_source"))
		line.data_detail = _cell(row, header_map.get("data_detail"))
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
		elif key in {"gia tri thang", "monthly value"}:
			mapping["monthly_value"] = idx
		elif key in {"nguon du lieu", "data source"}:
			mapping["data_source"] = idx
		elif key in {"chi tiet du lieu", "data detail"}:
			mapping["data_detail"] = idx
		elif key in {"thu tu", "sort order"}:
			mapping["sort_order"] = idx
		elif key in {"ghi chu", "note"}:
			mapping["note"] = idx
	return mapping


def _normalize_header(value):
	text = (value or "").strip().lower()
	text = unicodedata.normalize("NFKD", text)
	return "".join(char for char in text if not unicodedata.combining(char))


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


def _build_line_key(doi_tuong, ct_doi_tuong, chi_tiet_doi_tuong_c2, khoan_muc, ct):
	parts = [
		doi_tuong or "",
		ct_doi_tuong or "",
		chi_tiet_doi_tuong_c2 or "",
		khoan_muc or "",
		ct or "",
	]
	return "||".join(str(part).strip() for part in parts)


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
