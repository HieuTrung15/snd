from __future__ import annotations

import io
import json
from datetime import date

import frappe
from frappe import _
from frappe.utils import get_first_day, get_last_day, getdate
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


LABOR_FIELDS = (
	"begin_total",
	"begin_female",
	"increase_total",
	"increase_female",
	"decrease_total",
	"decrease_retire",
	"decrease_contract_end",
	"decrease_internal",
	"decrease_transfer",
	"end_total",
	"end_female",
	"contract_indef",
	"contract_def",
	"contract_probation",
	"contract_none",
	"contract_other",
)
PLAN_FIELDS = ("annual_labor_plan", "plan_achievement_pct", "plan_variance")
VALUE_FIELDS = (*LABOR_FIELDS, *PLAN_FIELDS)


def execute(filters=None):
	filters = _normalize_filters(filters)
	_validate_access()
	_validate_filters(filters)
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Bộ phận"), "fieldname": "department_name", "fieldtype": "Data", "width": 190},
		{"label": _("Đầu kỳ - Tổng số"), "fieldname": "begin_total", "fieldtype": "Int", "width": 105},
		{"label": _("Đầu kỳ - Trong đó nữ"), "fieldname": "begin_female", "fieldtype": "Int", "width": 115},
		{"label": _("Tăng - Tổng số"), "fieldname": "increase_total", "fieldtype": "Int", "width": 105},
		{"label": _("Tăng - Trong đó nữ"), "fieldname": "increase_female", "fieldtype": "Int", "width": 115},
		{"label": _("Giảm - Tổng số"), "fieldname": "decrease_total", "fieldtype": "Int", "width": 105},
		{"label": _("Giảm - Nghỉ hưu"), "fieldname": "decrease_retire", "fieldtype": "Int", "width": 105},
		{"label": _("Giảm - Chấm dứt HĐLĐ"), "fieldname": "decrease_contract_end", "fieldtype": "Int", "width": 135},
		{"label": _("Giảm - Điều động nội bộ"), "fieldname": "decrease_internal", "fieldtype": "Int", "width": 130},
		{"label": _("Giảm - Điều chuyển công tác"), "fieldname": "decrease_transfer", "fieldtype": "Int", "width": 145},
		{"label": _("Cuối kỳ - Tổng số"), "fieldname": "end_total", "fieldtype": "Int", "width": 105},
		{"label": _("Cuối kỳ - Trong đó nữ"), "fieldname": "end_female", "fieldtype": "Int", "width": 115},
		{"label": _("HĐLĐ - Không xác định thời hạn"), "fieldname": "contract_indef", "fieldtype": "Int", "width": 155},
		{"label": _("HĐLĐ - Xác định thời hạn"), "fieldname": "contract_def", "fieldtype": "Int", "width": 145},
		{"label": _("HĐLĐ - Thử việc"), "fieldname": "contract_probation", "fieldtype": "Int", "width": 105},
		{"label": _("HĐLĐ - Không giao kết"), "fieldname": "contract_none", "fieldtype": "Int", "width": 125},
		{"label": _("HĐLĐ - Khác"), "fieldname": "contract_other", "fieldtype": "Int", "width": 95},
		{"label": _("LĐ kế hoạch năm"), "fieldname": "annual_labor_plan", "fieldtype": "Int", "width": 120},
		{"label": _("% đạt KH"), "fieldname": "plan_achievement_pct", "fieldtype": "Percent", "width": 105},
		{"label": _("Thừa (+) / Thiếu (-)"), "fieldname": "plan_variance", "fieldtype": "Int", "width": 125},
	]


def get_data(filters=None):
	filters = _normalize_filters(filters)
	from_date, to_date = _get_period(filters)
	company = filters.company
	plan_from_date = date(to_date.year, 1, 1)
	plan_to_date = date(to_date.year, 12, 31)

	rows = frappe.db.sql(
		"""
		SELECT
			d.name AS department,
			COALESCE(NULLIF(d.department_name, ''), d.name) AS department_name,
			SUM(CASE WHEN e.date_of_joining < %(from_date)s
				AND (e.relieving_date IS NULL OR e.relieving_date >= %(from_date)s) THEN 1 ELSE 0 END) AS begin_total,
			SUM(CASE WHEN e.date_of_joining < %(from_date)s
				AND (e.relieving_date IS NULL OR e.relieving_date >= %(from_date)s)
				AND e.gender = 'Female' THEN 1 ELSE 0 END) AS begin_female,
			SUM(CASE WHEN e.date_of_joining BETWEEN %(from_date)s AND %(to_date)s THEN 1 ELSE 0 END) AS increase_total,
			SUM(CASE WHEN e.date_of_joining BETWEEN %(from_date)s AND %(to_date)s
				AND e.gender = 'Female' THEN 1 ELSE 0 END) AS increase_female,
			SUM(CASE WHEN e.relieving_date BETWEEN %(from_date)s AND %(to_date)s THEN 1 ELSE 0 END) AS decrease_total,
			SUM(CASE WHEN e.relieving_date BETWEEN %(from_date)s AND %(to_date)s
				AND LOWER(COALESCE(e.reason_for_leaving, '')) LIKE '%%nghỉ hưu%%' THEN 1 ELSE 0 END) AS decrease_retire,
			SUM(CASE WHEN e.relieving_date BETWEEN %(from_date)s AND %(to_date)s
				AND (LOWER(COALESCE(e.reason_for_leaving, '')) LIKE '%%chấm dứt%%'
					OR LOWER(COALESCE(e.reason_for_leaving, '')) LIKE '%%hết hạn%%') THEN 1 ELSE 0 END) AS decrease_contract_end,
			SUM(CASE WHEN e.relieving_date BETWEEN %(from_date)s AND %(to_date)s
				AND LOWER(COALESCE(e.reason_for_leaving, '')) LIKE '%%điều động nội bộ%%' THEN 1 ELSE 0 END) AS decrease_internal,
			SUM(CASE WHEN e.relieving_date BETWEEN %(from_date)s AND %(to_date)s
				AND LOWER(COALESCE(e.reason_for_leaving, '')) LIKE '%%điều chuyển công tác%%' THEN 1 ELSE 0 END) AS decrease_transfer,
			SUM(CASE WHEN e.date_of_joining <= %(to_date)s
				AND (e.relieving_date IS NULL OR e.relieving_date > %(to_date)s) THEN 1 ELSE 0 END) AS end_total,
			SUM(CASE WHEN e.date_of_joining <= %(to_date)s
				AND (e.relieving_date IS NULL OR e.relieving_date > %(to_date)s)
				AND e.gender = 'Female' THEN 1 ELSE 0 END) AS end_female,
			SUM(CASE WHEN e.date_of_joining <= %(to_date)s
				AND (e.relieving_date IS NULL OR e.relieving_date > %(to_date)s)
				AND e.employment_type = 'HĐLĐ không xác định thời hạn' THEN 1 ELSE 0 END) AS contract_indef,
			SUM(CASE WHEN e.date_of_joining <= %(to_date)s
				AND (e.relieving_date IS NULL OR e.relieving_date > %(to_date)s)
				AND e.employment_type = 'HĐLĐ xác định thời hạn' THEN 1 ELSE 0 END) AS contract_def,
			SUM(CASE WHEN e.date_of_joining <= %(to_date)s
				AND (e.relieving_date IS NULL OR e.relieving_date > %(to_date)s)
				AND e.employment_type = 'Hợp đồng thử việc' THEN 1 ELSE 0 END) AS contract_probation,
			SUM(CASE WHEN e.date_of_joining <= %(to_date)s
				AND (e.relieving_date IS NULL OR e.relieving_date > %(to_date)s)
				AND e.employment_type = 'Không giao kết HĐLĐ' THEN 1 ELSE 0 END) AS contract_none,
			plan.annual_labor_plan
		FROM `tabDepartment` d
		LEFT JOIN `tabEmployee` e
			ON e.department = d.name
			AND e.company = %(company)s
			AND e.status = 'Active'
		LEFT JOIN (
			SELECT
				sp.department,
				SUM(spd.number_of_positions) AS annual_labor_plan
			FROM `tabStaffing Plan` sp
			INNER JOIN `tabStaffing Plan Detail` spd
				ON spd.parent = sp.name
				AND spd.parenttype = 'Staffing Plan'
				AND spd.parentfield = 'staffing_details'
			WHERE sp.company = %(company)s
				AND sp.docstatus = 1
				AND sp.from_date <= %(plan_to_date)s
				AND sp.to_date >= %(plan_from_date)s
			GROUP BY sp.department
		) plan ON plan.department = d.name
		WHERE d.company = %(company)s AND d.disabled = 0
		GROUP BY d.name, d.department_name, d.lft, plan.annual_labor_plan
		ORDER BY d.lft ASC, d.department_name ASC
		""",
		{
			"company": company,
			"from_date": from_date,
			"to_date": to_date,
			"plan_from_date": plan_from_date,
			"plan_to_date": plan_to_date,
		},
		as_dict=True,
	)

	for index, row in enumerate(rows, 1):
		row["stt"] = index
		for fieldname in LABOR_FIELDS:
			if fieldname == "contract_other":
				continue
			row[fieldname] = int(row.get(fieldname) or 0)
		known_contracts = sum(
			row[fieldname]
			for fieldname in ("contract_indef", "contract_def", "contract_probation", "contract_none")
		)
		row["contract_other"] = max(row["end_total"] - known_contracts, 0)
		annual_labor_plan = row.get("annual_labor_plan")
		if annual_labor_plan is None:
			row["annual_labor_plan"] = None
			row["plan_achievement_pct"] = None
			row["plan_variance"] = None
		else:
			annual_labor_plan = int(annual_labor_plan)
			row["annual_labor_plan"] = annual_labor_plan
			row["plan_achievement_pct"] = (
				round(row["end_total"] / annual_labor_plan * 100, 2) if annual_labor_plan else None
			)
			row["plan_variance"] = row["end_total"] - annual_labor_plan

	return rows


def _get_totals(rows):
	totals = {
		fieldname: sum((row.get(fieldname) or 0) for row in rows)
		for fieldname in LABOR_FIELDS
	}
	planned_rows = [row for row in rows if row.get("annual_labor_plan") is not None]
	if not planned_rows:
		totals.update({fieldname: None for fieldname in PLAN_FIELDS})
		return totals

	annual_labor_plan = sum(int(row.get("annual_labor_plan") or 0) for row in planned_rows)
	planned_end_total = sum(int(row.get("end_total") or 0) for row in planned_rows)
	totals["annual_labor_plan"] = annual_labor_plan
	totals["plan_achievement_pct"] = (
		round(planned_end_total / annual_labor_plan * 100, 2) if annual_labor_plan else None
	)
	totals["plan_variance"] = planned_end_total - annual_labor_plan
	return totals


@frappe.whitelist()
def download_excel(filters=None):
	filters = _normalize_filters(filters)
	_validate_access()
	_validate_filters(filters)
	rows = get_data(filters)
	from_date, to_date = _get_period(filters)
	company_name = frappe.db.get_value("Company", filters.company, "company_name") or filters.company
	workbook = _make_workbook(company_name, from_date, to_date, rows)

	stream = io.BytesIO()
	workbook.save(stream)
	frappe.local.response.filename = (
		f"Tinh_hinh_su_dung_lao_dong_{from_date.strftime('%Y%m%d')}_{to_date.strftime('%Y%m%d')}.xlsx"
	)
	frappe.local.response.filecontent = stream.getvalue()
	frappe.local.response.type = "binary"


def _make_workbook(company_name, from_date, to_date, rows):
	workbook = Workbook()
	worksheet = workbook.active
	worksheet.title = "Tình hình sử dụng LĐ"
	worksheet.sheet_view.showGridLines = False
	worksheet.freeze_panes = "C11"
	worksheet.page_setup.orientation = "landscape"
	worksheet.page_setup.paperSize = worksheet.PAPERSIZE_A3
	worksheet.page_setup.fitToWidth = 1
	worksheet.sheet_properties.pageSetUpPr.fitToPage = True
	worksheet.print_title_rows = "7:10"

	worksheet.merge_cells("A1:G1")
	worksheet["A1"] = str(company_name).upper()
	worksheet.merge_cells("O1:U1")
	worksheet["O1"] = "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"
	worksheet.merge_cells("O2:U2")
	worksheet["O2"] = "Độc lập - Tự do - Hạnh phúc"
	worksheet.merge_cells("A4:U4")
	worksheet["A4"] = "BÁO CÁO TÌNH HÌNH SỬ DỤNG LAO ĐỘNG"
	worksheet.merge_cells("A5:U5")
	worksheet["A5"] = f"Từ ngày {from_date.strftime('%d-%m-%Y')} đến ngày {to_date.strftime('%d-%m-%Y')}"

	worksheet.merge_cells("A7:A10")
	worksheet["A7"] = "STT"
	worksheet.merge_cells("B7:B10")
	worksheet["B7"] = "Bộ phận"
	worksheet.merge_cells("C7:R7")
	worksheet["C7"] = "Tình hình sử dụng lao động"
	worksheet.merge_cells("S7:U7")
	worksheet["S7"] = "Kế hoạch & đánh giá thực hiện"
	worksheet.merge_cells("C8:D8")
	worksheet["C8"] = "Số lao động đầu kỳ"
	worksheet.merge_cells("E8:F8")
	worksheet["E8"] = "Số lao động tăng trong kỳ"
	worksheet.merge_cells("G8:K8")
	worksheet["G8"] = "Số lao động giảm trong kỳ"
	worksheet.merge_cells("L8:R8")
	worksheet["L8"] = "Số lao động cuối kỳ"
	worksheet.merge_cells("S8:S10")
	worksheet["S8"] = "LĐ kế hoạch năm"
	worksheet.merge_cells("T8:U8")
	worksheet["T8"] = "So sánh với kế hoạch"
	worksheet.merge_cells("T9:T10")
	worksheet["T9"] = "% đạt KH"
	worksheet.merge_cells("U9:U10")
	worksheet["U9"] = "Thừa (+) / Thiếu (-)"

	for column, label in (("C", "Tổng số"), ("D", "Trong đó nữ"), ("E", "Tổng số"), ("F", "Trong đó nữ"), ("G", "Số lao động giảm"), ("L", "Tổng số"), ("M", "Trong đó nữ")):
		worksheet.merge_cells(f"{column}9:{column}10")
		worksheet[f"{column}9"] = label
	worksheet.merge_cells("H9:K9")
	worksheet["H9"] = "Trong đó"
	worksheet.merge_cells("N9:R9")
	worksheet["N9"] = "Loại hợp đồng lao động"

	for column, label in zip(
		(8, 9, 10, 11, 14, 15, 16, 17, 18),
		(
			"Nghỉ hưu",
			"Chấm dứt HĐLĐ",
			"Điều động nội bộ",
			"Điều chuyển công tác",
			"Không xác định thời hạn",
			"Xác định thời hạn",
			"Thử việc",
			"Không giao kết HĐLĐ",
			"Khác",
		),
	):
		worksheet.cell(row=10, column=column, value=label)

	data_fields = ("stt", "department_name", *VALUE_FIELDS)
	start_row = 11
	for row_index, row in enumerate(rows, start_row):
		for column_index, fieldname in enumerate(data_fields, 1):
			worksheet.cell(row=row_index, column=column_index, value=row.get(fieldname))

	total_row = start_row + len(rows)
	worksheet.cell(row=total_row, column=1, value="")
	worksheet.cell(row=total_row, column=2, value="TỔNG CỘNG")
	totals = _get_totals(rows)
	for column_index, fieldname in enumerate(VALUE_FIELDS, 3):
		worksheet.cell(row=total_row, column=column_index, value=totals[fieldname])

	for row_index in range(start_row, total_row + 1):
		percentage_cell = worksheet.cell(row=row_index, column=20)
		percentage_cell.number_format = "0.00%"
		if percentage_cell.value is not None:
			percentage_cell.value /= 100

	thin = Side(style="thin", color="000000")
	border = Border(left=thin, right=thin, top=thin, bottom=thin)
	header_fill = PatternFill("solid", fgColor="C6D9F5")
	plan_header_fill = PatternFill("solid", fgColor="F3F7A1")
	total_fill = PatternFill("solid", fgColor="D9EAF7")
	center = Alignment(horizontal="center", vertical="center", wrap_text=True)
	left = Alignment(horizontal="left", vertical="center", wrap_text=True)

	for cell_ref in ("A1", "O1", "O2", "A4", "A5"):
		cell = worksheet[cell_ref]
		cell.font = Font(name="Times New Roman", size=11, bold=True)
		cell.alignment = center
	worksheet["A1"].alignment = left
	worksheet["A4"].font = Font(name="Times New Roman", size=13, bold=True)

	for row in worksheet.iter_rows(min_row=7, max_row=10, min_col=1, max_col=21):
		for cell in row:
			cell.fill = header_fill
			cell.border = border
			cell.font = Font(name="Times New Roman", size=9, bold=True, color="000080")
			cell.alignment = center
	for row in worksheet.iter_rows(min_row=7, max_row=10, min_col=19, max_col=21):
		for cell in row:
			cell.fill = plan_header_fill

	for row in worksheet.iter_rows(min_row=start_row, max_row=total_row, min_col=1, max_col=21):
		for cell in row:
			cell.border = border
			cell.font = Font(name="Times New Roman", size=9, bold=cell.row == total_row)
			cell.alignment = left if cell.column == 2 else center
			if cell.row == total_row:
				cell.fill = total_fill

	widths = (6, 27, 11, 11, 11, 11, 11, 12, 14, 13, 15, 11, 11, 16, 15, 11, 15, 10, 13, 11, 15)
	for column_index, width in enumerate(widths, 1):
		worksheet.column_dimensions[get_column_letter(column_index)].width = width
	for row_index, height in {1: 22, 2: 20, 4: 24, 5: 20, 7: 23, 8: 26, 9: 28, 10: 46}.items():
		worksheet.row_dimensions[row_index].height = height

	return workbook


def _normalize_filters(filters):
	if isinstance(filters, str):
		filters = json.loads(filters or "{}")
	return frappe._dict(filters or {})


def _get_period(filters):
	today = getdate()
	from_date = getdate(filters.get("from_date") or get_first_day(today))
	to_date = getdate(filters.get("to_date") or get_last_day(today))
	return from_date, to_date


def _validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Vui lòng chọn Công ty."))
	if not frappe.db.exists("Company", filters.company):
		frappe.throw(_("Công ty không tồn tại."))
	from_date, to_date = _get_period(filters)
	if from_date > to_date:
		frappe.throw(_("Từ ngày không được lớn hơn Đến ngày."))


def _validate_access():
	frappe.has_permission("Employee", ptype="read", throw=True)
	frappe.has_permission("Department", ptype="read", throw=True)
