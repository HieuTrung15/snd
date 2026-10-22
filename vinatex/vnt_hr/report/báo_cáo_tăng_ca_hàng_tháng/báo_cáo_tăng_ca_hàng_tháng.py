"""Monthly overtime report matching the visible layout of BCC thêm giờ T10."""

from __future__ import annotations

import io

import frappe
from frappe import _
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from vinatex.vnt_hr.report.monthly_report_common import (
	build_monthly_context,
	compact_number,
	confirmation_url,
	excel_content_width,
	group_rows,
)


REPORT_NAME = "Báo cáo tăng ca hàng tháng"
TOTAL_COLUMNS = (
	("tot_overtime_normal", "Ngày thường", 12),
	("tot_overtime_off", "Ngày nghỉ", 10),
	("tot_overtime_holiday", "Ngày lễ", 10),
)
STATE_FILLS = {
	"unreviewed": "FFF2CC",
	"pending": "FFFF9900",
	"approved": "C6E0B4",
	"approved_incomplete": "FCE4D6",
	"rejected": "F4CCCC",
}


def execute(filters=None):
	context = _build_context(filters)
	return _get_columns(context.days), context.rows, _message()


@frappe.whitelist()
def download_excel(filters=None):
	context = _build_context(filters)
	workbook = _make_workbook(context)
	stream = io.BytesIO()
	workbook.save(stream)
	frappe.local.response.filename = (
		f"Bao_cao_tang_ca_hang_thang_{context.from_date.strftime('%m-%Y')}.xlsx"
	)
	frappe.local.response.filecontent = stream.getvalue()
	frappe.local.response.type = "binary"


def _build_context(filters=None):
	context = build_monthly_context(filters)
	for row in context.rows:
		for day in context.days:
			fieldname = f"d{day.day:02d}"
			hours = compact_number(row.get(f"{fieldname}__overtime") or 0)
			row[fieldname] = hours if hours else ""
			row[f"{fieldname}__state"] = (
				(row.get(f"{fieldname}__review_state") or "unreviewed") if hours else ""
			)
			if hours and not row.get(f"{fieldname}__label"):
				row[f"{fieldname}__label"] = "Giờ tăng ca tính từ dữ liệu chấm công"
	return context


def _get_columns(days):
	columns = [
		{"fieldname": "employee_name", "label": _("Tên nhân viên"), "fieldtype": "Data", "width": 180},
		{"fieldname": "employee_code", "label": _("Mã nhân viên"), "fieldtype": "Data", "width": 110},
		{"fieldname": "department", "label": _("Vị trí / Bộ phận"), "fieldtype": "Data", "width": 150},
		{"fieldname": "shift_label", "label": _("Kíp"), "fieldtype": "Data", "width": 90},
	]
	columns.extend(
		{
			"fieldname": f"d{day.day:02d}",
			"label": str(day.day),
			"fieldtype": "Float",
			"width": 48,
		}
		for day in days
	)
	columns.extend(
		{"fieldname": fieldname, "label": _(label), "fieldtype": "Float", "width": width * 8}
		for fieldname, label, width in TOTAL_COLUMNS
	)
	return columns


def _make_workbook(context):
	workbook = Workbook()
	worksheet = workbook.active
	worksheet.title = "Tăng ca"
	worksheet.sheet_view.showGridLines = False
	worksheet.freeze_panes = "F4"
	worksheet.page_setup.orientation = "landscape"
	worksheet.page_setup.fitToWidth = 1
	worksheet.page_setup.fitToHeight = 0
	worksheet.sheet_properties.pageSetUpPr.fitToPage = True

	styles = _excel_styles()
	static_headers = (
		("Stt", 6),
		(
			"Tên nhân viên",
			excel_content_width(
				["Tên nhân viên", *(row.employee_name for row in context.rows)],
				minimum=18,
				maximum=36,
			),
		),
		(
			"Mã nhân viên",
			excel_content_width(
				["Mã nhân viên", *(row.employee_code for row in context.rows)],
				minimum=13,
				maximum=20,
			),
		),
		(
			"Vị trí/ Bộ phận công tác",
			excel_content_width(
				[row.department_code for row in context.rows],
				minimum=10,
				maximum=22,
			),
		),
		(
			"Kíp",
			excel_content_width(
				["Kíp", *(row.shift_label for row in context.rows)],
				minimum=12,
				maximum=42,
			),
		),
	)
	day_start = len(static_headers) + 1
	day_end = day_start + len(context.days) - 1
	total_start = day_end + 1
	last_column = total_start + len(TOTAL_COLUMNS) - 1

	for column, (label, width) in enumerate(static_headers, start=1):
		worksheet.column_dimensions[get_column_letter(column)].width = width
		if column == 5:
			continue
		if column == 4:
			worksheet.merge_cells(start_row=1, start_column=4, end_row=2, end_column=5)
			_set_header(worksheet, 1, 4, label, styles)
			_style_range(worksheet, 1, 4, 2, 5, styles.header_fill, styles.border)
			continue
		worksheet.merge_cells(start_row=1, start_column=column, end_row=2, end_column=column)
		_set_header(worksheet, 1, column, label, styles)
		_style_range(worksheet, 1, column, 2, column, styles.header_fill, styles.border)

	title_day_end = day_end - 1 if len(context.days) == 31 else day_end
	worksheet.merge_cells(start_row=1, start_column=day_start, end_row=1, end_column=title_day_end)
	_set_header(
		worksheet,
		1,
		day_start,
		f"T {context.from_date.month}/{context.from_date.year}",
		styles,
	)
	_style_range(worksheet, 1, day_start, 1, day_end, styles.header_fill, styles.border)
	for offset, day in enumerate(context.days):
		column = day_start + offset
		worksheet.column_dimensions[get_column_letter(column)].width = 4.2
		cell = worksheet.cell(2, column, day.day)
		cell.font = styles.header_font
		cell.alignment = styles.center
		cell.fill = styles.sunday_fill if day.weekday() == 6 else styles.header_fill
		cell.border = styles.border

	for offset, (_fieldname, label, width) in enumerate(TOTAL_COLUMNS):
		column = total_start + offset
		worksheet.column_dimensions[get_column_letter(column)].width = width
		worksheet.merge_cells(start_row=1, start_column=column, end_row=2, end_column=column)
		_set_header(worksheet, 1, column, label, styles)
		_style_range(worksheet, 1, column, 2, column, styles.header_fill, styles.border)

	worksheet.row_dimensions[1].height = 40
	worksheet.row_dimensions[2].height = 24
	current_row = 4
	sequence = 0
	for section, subgroups in group_rows(context.rows).items():
		current_row = _append_group_row(worksheet, current_row, section, last_column, styles)
		for subgroup, employee_rows in subgroups.items():
			if subgroup:
				current_row = _append_group_row(worksheet, current_row, subgroup, last_column, styles)
			for row in employee_rows:
				sequence += 1
				values = [
					sequence,
					row.employee_name,
					row.employee_code,
					row.department_code,
					row.shift_label,
				]
				for column, value in enumerate(values, start=1):
					cell = worksheet.cell(current_row, column, value)
					_style_data_cell(cell, styles, text=column == 2)
				for offset, day in enumerate(context.days):
					fieldname = f"d{day.day:02d}"
					cell = worksheet.cell(current_row, day_start + offset, row.get(fieldname) or "")
					_style_data_cell(cell, styles)
					state = row.get(f"{fieldname}__state")
					if state in STATE_FILLS:
						cell.fill = PatternFill("solid", fgColor=STATE_FILLS[state])
					if row.get(f"{fieldname}__confirmation"):
						cell.hyperlink = confirmation_url(row.get(f"{fieldname}__confirmation"))
						cell.font = Font(name="Arial", size=9, bold=True, color="0563C1", underline="single")
				for offset, (fieldname, _label, _width) in enumerate(TOTAL_COLUMNS):
					cell = worksheet.cell(
						current_row,
						total_start + offset,
						compact_number(row.get(fieldname)),
					)
					_style_data_cell(cell, styles)
				worksheet.row_dimensions[current_row].height = 22
				current_row += 1

	total_row = current_row
	worksheet.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=5)
	worksheet.cell(total_row, 1, "TỔNG")
	for column in range(1, last_column + 1):
		cell = worksheet.cell(total_row, column)
		cell.fill = styles.total_fill
		cell.border = styles.border
		cell.font = styles.total_font
		cell.alignment = styles.center
	for offset, (fieldname, _label, _width) in enumerate(TOTAL_COLUMNS):
		cell = worksheet.cell(
			total_row,
			total_start + offset,
			compact_number(sum(float(row.get(fieldname) or 0) for row in context.rows)),
		)
		cell.fill = styles.total_fill
		cell.border = styles.border
		cell.font = styles.total_font
		cell.alignment = styles.center

	_append_signatures(worksheet, total_row + 1, last_column, context.to_date.year, styles)
	worksheet.auto_filter.ref = f"A3:{get_column_letter(last_column)}{total_row}"
	worksheet.print_title_rows = "1:2"
	return workbook


def _excel_styles():
	thin = Side(style="thin", color="000000")
	return frappe._dict(
		border=Border(left=thin, right=thin, top=thin, bottom=thin),
		header_fill=PatternFill("solid", fgColor="F2DBDB"),
		sunday_fill=PatternFill("solid", fgColor="FF0000"),
		group_fill=PatternFill("solid", fgColor="D99594"),
		total_fill=PatternFill("solid", fgColor="D9EAD3"),
		header_font=Font(name="Arial", size=9, bold=True),
		data_font=Font(name="Arial", size=9),
		total_font=Font(name="Arial", size=9, bold=True),
		center=Alignment(horizontal="center", vertical="center", wrap_text=True),
		left=Alignment(horizontal="left", vertical="center", wrap_text=True),
	)


def _set_header(worksheet, row, column, value, styles):
	cell = worksheet.cell(row, column, value)
	cell.font = styles.header_font
	cell.alignment = styles.center
	cell.fill = styles.header_fill
	cell.border = styles.border


def _style_range(worksheet, row1, column1, row2, column2, fill, border):
	for row in worksheet.iter_rows(
		min_row=row1, max_row=row2, min_col=column1, max_col=column2
	):
		for cell in row:
			cell.fill = fill
			cell.border = border


def _style_data_cell(cell, styles, *, text=False):
	cell.font = styles.data_font
	cell.alignment = styles.left if text else styles.center
	cell.border = styles.border
	cell.fill = PatternFill("solid", fgColor="FFFFFF")


def _append_group_row(worksheet, row, label, last_column, styles):
	worksheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_column)
	worksheet.cell(row, 1, label)
	for column in range(1, last_column + 1):
		cell = worksheet.cell(row, column)
		cell.fill = styles.group_fill
		cell.border = styles.border
		cell.font = styles.total_font
		cell.alignment = styles.left
	return row + 1


def _append_signatures(worksheet, row, last_column, year, styles):
	third = max(4, last_column // 3)
	date_start = max(1, last_column - third + 1)
	worksheet.merge_cells(start_row=row, start_column=date_start, end_row=row, end_column=last_column)
	date_cell = worksheet.cell(row, date_start, f"Ninh Bình, ngày     tháng     năm {year}")
	date_cell.font = Font(name="Times New Roman", size=10, italic=True)
	date_cell.alignment = styles.center
	for column, label in (
		(1, "GIÁM ĐỐC"),
		(third + 1, "P. TÀI CHÍNH KẾ TOÁN"),
		(2 * third + 1, "NGƯỜI LẬP BIỂU"),
	):
		worksheet.merge_cells(
			start_row=row + 1,
			start_column=column,
			end_row=row + 1,
			end_column=min(last_column, column + third - 1),
		)
		cell = worksheet.cell(row + 1, column, label)
		cell.font = Font(name="Times New Roman", size=10, bold=True)
		cell.alignment = styles.center
	for column, name in (
		(1, "PHẠM NGỌC BÌNH"),
		(third + 1, "PHẠM ANH TUẤN"),
		(2 * third + 1, "ĐOÀN THỊ HỒNG NHUNG"),
	):
		worksheet.merge_cells(
			start_row=row + 4,
			start_column=column,
			end_row=row + 4,
			end_column=min(last_column, column + third - 1),
		)
		cell = worksheet.cell(row + 4, column, name)
		cell.font = Font(name="Times New Roman", size=10, bold=True)
		cell.alignment = styles.center


def _message():
	return (
		"<div><strong>Giờ tăng ca</strong> được làm tròn theo dữ liệu "
		"vân tay và ca kế hoạch. Ô có màu/huy hiệu HR có thể bấm để mở phiếu giải trình.</div>"
	)

