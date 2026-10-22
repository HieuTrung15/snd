"""Monthly attendance report matching the visible layout of BCC T10-2026."""

from __future__ import annotations

import io

import frappe
from frappe import _
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from vinatex.vnt_hr.report.monthly_report_common import (
	ANOMALY_STATES,
	build_monthly_context,
	compact_number,
	confirmation_url,
	excel_content_width,
	group_rows,
)


REPORT_NAME = "Báo cáo công hàng tháng"
SUMMARY_COLUMNS = (
	("tot_work_days", "X (S,C) + CT", 12),
	("tot_work_hours", "h làm việc", 11),
	("tot_sick", "Ô", 6),
	("tot_night", "Đ", 6),
	("tot_sunday", "CN", 6),
	("tot_holiday", "L", 6),
	("tot_special_group", "NL, NM, CTDH", 12),
	("tot_paid_group", "P, ND, CL", 10),
	("tot_family_leave", "CH, TL", 9),
	("tot_comp_leave", "NB", 6),
	("tot_unpaid_reason", "R0", 6),
	("tot_unpaid_no_reason", "L0", 6),
	("rating", "Xếp loại", 10),
	("score", "Điểm", 8),
)


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
		f"Bao_cao_cong_hang_thang_{context.from_date.strftime('%m-%Y')}.xlsx"
	)
	frappe.local.response.filecontent = stream.getvalue()
	frappe.local.response.type = "binary"


def _build_context(filters=None):
	context = build_monthly_context(filters)
	for row in context.rows:
		row.tot_special_group = float(row.tot_public_holiday or 0) + float(
			row.tot_special_leave or 0
		)
		row.tot_paid_group = float(row.tot_paid_leave or 0)
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
			"fieldtype": "Data",
			"width": 48,
		}
		for day in days
	)
	columns.extend(
		{"fieldname": fieldname, "label": _(label), "fieldtype": "Data", "width": width * 8}
		for fieldname, label, width in SUMMARY_COLUMNS
	)
	return columns


def _make_workbook(context):
	workbook = Workbook()
	worksheet = workbook.active
	worksheet.title = f"BCC T{context.from_date.month}-{context.from_date.year}"
	worksheet.sheet_view.showGridLines = False
	worksheet.freeze_panes = "D4"
	worksheet.page_setup.orientation = "landscape"
	worksheet.page_setup.fitToWidth = 1
	worksheet.page_setup.fitToHeight = 0
	worksheet.sheet_properties.pageSetUpPr.fitToPage = True

	styles = _excel_styles()
	static_headers = (
		("STT", 6),
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
	day_start_column = len(static_headers) + 1
	day_end_column = day_start_column + len(context.days) - 1
	summary_start_column = day_end_column + 1
	last_column = summary_start_column + len(SUMMARY_COLUMNS) - 1

	for column_index, (label, width) in enumerate(static_headers, start=1):
		worksheet.column_dimensions[get_column_letter(column_index)].width = width
		if column_index == 5:
			continue
		if column_index == 4:
			worksheet.merge_cells(start_row=1, start_column=4, end_row=2, end_column=5)
			_set_header_cell(worksheet, 1, 4, label, styles)
			_style_range(worksheet, 1, 4, 2, 5, styles.header_fill, styles.border)
			continue
		worksheet.merge_cells(start_row=1, start_column=column_index, end_row=2, end_column=column_index)
		_set_header_cell(worksheet, 1, column_index, label, styles)
		_style_range(worksheet, 1, column_index, 2, column_index, styles.header_fill, styles.border)

	title_day_end_column = day_end_column - 1 if len(context.days) == 31 else day_end_column
	worksheet.merge_cells(
		start_row=1,
		start_column=day_start_column,
		end_row=1,
		end_column=title_day_end_column,
	)
	_set_header_cell(
		worksheet,
		1,
		day_start_column,
		f"T {context.from_date.month}/{context.from_date.year}",
		styles,
	)
	_style_range(
		worksheet,
		1,
		day_start_column,
		1,
		day_end_column,
		styles.header_fill,
		styles.border,
	)
	for offset, day in enumerate(context.days):
		column = day_start_column + offset
		worksheet.column_dimensions[get_column_letter(column)].width = 4.2
		cell = worksheet.cell(2, column, day.day)
		cell.font = styles.header_font
		cell.alignment = styles.center
		cell.fill = styles.sunday_fill if day.weekday() == 6 else styles.header_fill
		cell.border = styles.border

	for offset, (_fieldname, label, width) in enumerate(SUMMARY_COLUMNS):
		column = summary_start_column + offset
		worksheet.column_dimensions[get_column_letter(column)].width = width
		worksheet.merge_cells(start_row=1, start_column=column, end_row=2, end_column=column)
		_set_header_cell(worksheet, 1, column, label, styles)
		_style_range(worksheet, 1, column, 2, column, styles.header_fill, styles.border)

	worksheet.row_dimensions[1].height = 40
	worksheet.row_dimensions[2].height = 24
	current_row = 4
	sequence = 0
	for section, subgroups in group_rows(context.rows).items():
		current_row = _append_group_row(
			worksheet, current_row, section, last_column, styles
		)
		for subgroup, employee_rows in subgroups.items():
			if subgroup:
				current_row = _append_group_row(
					worksheet, current_row, subgroup, last_column, styles
				)
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
					cell = worksheet.cell(current_row, day_start_column + offset, row.get(fieldname) or "")
					_style_data_cell(cell, styles)
					state = row.get(f"{fieldname}__state")
					if state in ANOMALY_STATES:
						cell.fill = PatternFill("solid", fgColor=ANOMALY_STATES[state]["fill"])
						cell.font = Font(name="Arial", size=9, bold=True, color="000000")
					if row.get(f"{fieldname}__confirmation"):
						cell.hyperlink = confirmation_url(row.get(f"{fieldname}__confirmation"))
						cell.font = Font(name="Arial", size=9, bold=True, color="0563C1", underline="single")
				for offset, (fieldname, _label, _width) in enumerate(SUMMARY_COLUMNS):
					value = row.get(fieldname)
					cell = worksheet.cell(
						current_row,
						summary_start_column + offset,
						compact_number(value) if fieldname not in ("rating", "score") else value,
					)
					_style_data_cell(cell, styles)
					if fieldname == "tot_work_hours":
						cell.number_format = "0.00"
				worksheet.row_dimensions[current_row].height = 22
				current_row += 1

	total_row = current_row
	worksheet.merge_cells(start_row=total_row, start_column=1, end_row=total_row, end_column=5)
	worksheet.cell(total_row, 1, "TỔNG CỘNG")
	for column in range(1, last_column + 1):
		cell = worksheet.cell(total_row, column)
		cell.fill = styles.total_fill
		cell.border = styles.border
		cell.font = styles.total_font
		cell.alignment = styles.center
	for offset, (fieldname, _label, _width) in enumerate(SUMMARY_COLUMNS):
		if fieldname in ("rating", "score"):
			continue
		column = summary_start_column + offset
		cell = worksheet.cell(
			total_row,
			column,
			compact_number(sum(float(row.get(fieldname) or 0) for row in context.rows)),
		)
		cell.fill = styles.total_fill
		cell.border = styles.border
		cell.font = styles.total_font
		cell.alignment = styles.center
		if fieldname == "tot_work_hours":
			cell.number_format = "0.00"

	legend_start = total_row + 1
	_append_legend(worksheet, legend_start, last_column, styles)
	signature_start = legend_start + 5
	_append_signatures(worksheet, signature_start, last_column, context.to_date.year, styles)
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


def _set_header_cell(worksheet, row, column, value, styles):
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
	worksheet.row_dimensions[row].height = 21
	return row + 1


def _append_legend(worksheet, start_row, last_column, styles):
	legend = [
		(("R0", "Nghỉ không hưởng lương (có lý do)"), ("1-7", "Thời gian làm việc không đủ công"), ("C", "Đi làm ca chiều (14h - 22h)")),
		(("L0", "Nghỉ không lý do"), ("CN", "Đi làm chủ nhật (ca hành chính)"), ("Đ", "Đi làm ca đêm (22h - 6h)")),
		(("X", "Đi làm (ca hành chính)"), ("S", "Đi làm ca sáng (6h - 14h)"), ("NB", "Nghỉ bù")),
		(("Ô", "Nghỉ ốm"), ("L / NL", "Lễ / Nghỉ lễ"), ("NM", "Nghỉ mát")),
		(("CH", "Cưới hỏi"), ("TL", "Tang lễ"), ("P", "Nghỉ phép")),
	]
	block_width = max(6, last_column // 3)
	for row_offset, entries in enumerate(legend):
		for block, (code, description) in enumerate(entries):
			column = 1 + block * block_width
			worksheet.cell(start_row + row_offset, column, code)
			worksheet.cell(start_row + row_offset, column + 1, ":")
			end_column = min(last_column, column + block_width - 1)
			if end_column >= column + 2:
				worksheet.merge_cells(
					start_row=start_row + row_offset,
					start_column=column + 2,
					end_row=start_row + row_offset,
					end_column=end_column,
				)
			worksheet.cell(start_row + row_offset, column + 2, description)
			worksheet.cell(start_row + row_offset, column).font = styles.total_font
			worksheet.cell(start_row + row_offset, column).alignment = styles.center
			worksheet.cell(start_row + row_offset, column + 1).alignment = styles.center
			worksheet.cell(start_row + row_offset, column + 2).font = Font(
				name="Times New Roman", size=10, italic=True, bold=True
			)
			worksheet.cell(start_row + row_offset, column + 2).alignment = styles.left


def _append_signatures(worksheet, row, last_column, year, styles):
	third = max(4, last_column // 3)
	date_start = max(1, last_column - third + 1)
	worksheet.merge_cells(start_row=row, start_column=date_start, end_row=row, end_column=last_column)
	date_cell = worksheet.cell(row, date_start, f"Ninh Bình, ngày     tháng     năm {year}")
	date_cell.font = Font(name="Times New Roman", size=10, italic=True)
	date_cell.alignment = styles.center
	labels = ((1, "GIÁM ĐỐC"), (third + 1, "P. TÀI CHÍNH KẾ TOÁN"), (2 * third + 1, "NGƯỜI LẬP BIỂU"))
	for column, label in labels:
		end_column = min(last_column, column + third - 1)
		worksheet.merge_cells(start_row=row + 1, start_column=column, end_row=row + 1, end_column=end_column)
		cell = worksheet.cell(row + 1, column, label)
		cell.font = Font(name="Times New Roman", size=10, bold=True)
		cell.alignment = styles.center
	for column, name in (
		(1, "PHẠM NGỌC BÌNH"),
		(third + 1, "PHẠM ANH TUẤN"),
		(2 * third + 1, "ĐOÀN THỊ HỒNG NHUNG"),
	):
		end_column = min(last_column, column + third - 1)
		worksheet.merge_cells(
			start_row=row + 4,
			start_column=column,
			end_row=row + 4,
			end_column=end_column,
		)
		cell = worksheet.cell(row + 4, column, name)
		cell.font = Font(name="Times New Roman", size=10, bold=True)
		cell.alignment = styles.center


def _message():
	return (
		"<div class='vnt-monthly-report-message'>"
		"<strong>Màu cần giải trình:</strong> "
		"<span style='background:#f59e0b;padding:2px 7px'>Cam: không có giờ vào</span> "
		"<span style='background:#fde047;padding:2px 7px'>Vàng: không có giờ ra</span> "
		"<span style='background:#ef4444;color:#fff;padding:2px 7px'>Đỏ: ngày phải đi làm nhưng không có vân tay</span>"
		"</div>"
	)

