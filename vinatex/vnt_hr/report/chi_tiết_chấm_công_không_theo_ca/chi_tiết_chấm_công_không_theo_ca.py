"""Chi tiết dữ liệu chấm công thô theo mẫu bảng công nhà máy.

Báo cáo nà cố ý không phụ thuộc Attendance và không yêu cầu bật
Enable Auto Attendance. Nguồn giờ là Employee Checkin; ca kế hoạch chỉ
được dùng để gán đúng ngày công cho ca qua đêm.
"""

from __future__ import annotations

import io
import json
import re
import unicodedata
from collections import OrderedDict, defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from vinatex.vnt_hr.attendance_processing import (
	build_shift_windows,
	load_checkins_for_windows,
)


REPORT_NAME = "Chi tiết chấm công không theo ca"
MAX_REPORT_DAYS = 62
STANDARD_WORKDAY_HOURS = Decimal("8")
HOURS_PER_MINUTE = Decimal("60")
DISPLAY_PRECISION = Decimal("0.001")
DUPLICATE_PUNCH_MINUTES = 5
ALLOWED_ROLES = {"System Manager", "HR User", "HR Manager"}

HEADERS = (
	("stt", "STT", 8),
	("employee_code", "Mã N.Viên", 15),
	("employee_name", "Tên N.Viên", 25),
	("display_department", "Phòng ban", 15),
	("designation", "Chức vụ", 15),
	("work_date", "Ngày", 12),
	("weekday_label", "Thứ", 8),
	("in_1", "Vào 1", 8),
	("out_1", "Ra 1", 8),
	("in_2", "Vào 2", 8),
	("out_2", "Ra 2", 8),
	("total_hours", "Tổng giờ", 12),
	("workdays", "Ngày Công", 12),
	("tc1", "TC1", 8),
	("tc2", "TC2", 8),
	("tc3", "TC3", 8),
	("grand_total", "Tổng cộng", 12),
)

# Các bộ phận khối văn phòng trong cơ cấu hiện tại. Nhóm còn lại
# không thuộc kíp được xếp vào HC và chia theo phòng ban, giống file mẫu.
OFFICE_DEPARTMENTS = {
	"ban giam doc",
	"ke toan",
	"tai chinh - ke toan",
	"kinh doanh",
	"lai xe",
	"nhan su",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate_access()
	context = _build_report_context(filters)
	return get_columns(), context.rows


def get_columns():
	fieldtypes = {
		"work_date": "Date",
		"total_hours": "Float",
		"workdays": "Float",
		"tc1": "Float",
		"tc2": "Float",
		"tc3": "Float",
		"grand_total": "Float",
	}
	return [
		{
			"fieldname": fieldname,
			"label": label,
			"fieldtype": fieldtypes.get(fieldname, "Data"),
			"width": width * 8,
			"precision": 3 if fieldname in fieldtypes and fieldname != "work_date" else None,
		}
		for fieldname, label, width in HEADERS
	]


@frappe.whitelist()
def download_excel(filters=None):
	"""Tạo tệp Excel có nhóm/tiêu đề giống file bàn giao của HR."""
	_validate_access()
	filters = frappe._dict(_parse_filters(filters))
	context = _build_report_context(filters)
	workbook = _make_workbook(context)

	stream = io.BytesIO()
	workbook.save(stream)
	from_date = getdate(context.from_date).isoformat()
	to_date = getdate(context.to_date).isoformat()
	frappe.local.response.filename = (
		f"Chi_tiet_cham_cong_khong_theo_ca_{from_date}_{to_date}.xlsx"
	)
	frappe.local.response.filecontent = stream.getvalue()
	frappe.local.response.type = "binary"


def _build_report_context(filters):
	from_date, to_date = _validate_filters(filters)
	employees = _get_employees(filters, from_date, to_date)
	company_name = filters.company
	if not employees:
		return frappe._dict(
			rows=[],
			company_name=company_name,
			from_date=from_date,
			to_date=to_date,
			employee_count=0,
			extra_punch_count=0,
		)

	windows = build_shift_windows(employees, from_date, to_date)
	employees = _apply_group_filters(employees, windows, filters, to_date)
	if not employees:
		return frappe._dict(
			rows=[],
			company_name=company_name,
			from_date=from_date,
			to_date=to_date,
			employee_count=0,
			extra_punch_count=0,
		)

	allowed_names = {employee.name for employee in employees}
	windows = {
		key: window for key, window in windows.items() if key[0] in allowed_names
	}
	assigned, unplanned = load_checkins_for_windows(
		employees, windows, from_date, to_date
	)
	punch_map, duplicate_map = _combine_checkins(
		assigned, unplanned, windows, from_date, to_date
	)

	employee_groups = {
		employee.name: _employee_group(employee, windows, to_date)
		for employee in employees
	}
	employees = sorted(
		employees,
		key=lambda employee: (
			_section_order(employee_groups[employee.name][0]),
			_natural_key(employee_groups[employee.name][1]),
			_natural_key(employee.employee_name or employee.name),
		),
	)

	rows = []
	extra_punch_count = 0
	duplicate_punch_count = 0
	sequence_by_group = defaultdict(int)
	for employee in employees:
		section, subgroup = employee_groups[employee.name]
		group_key = (section, subgroup)
		sequence_by_group[group_key] += 1
		sequence = sequence_by_group[group_key]
		for work_date in _date_range(from_date, to_date):
			logs = punch_map.get((employee.name, work_date), [])
			row = _make_detail_row(
				employee,
				work_date,
				logs,
				duplicate_logs=duplicate_map.get((employee.name, work_date), []),
				section=section,
				subgroup=subgroup,
				sequence=sequence,
				company_name=company_name,
				from_date=from_date,
				to_date=to_date,
			)
			extra_punch_count += row.extra_punch_count
			duplicate_punch_count += row.duplicate_punch_count
			rows.append(row)

	return frappe._dict(
		rows=rows,
		company_name=company_name,
		from_date=from_date,
		to_date=to_date,
		employee_count=len(employees),
		extra_punch_count=extra_punch_count,
		duplicate_punch_count=duplicate_punch_count,
	)


def _get_employees(filters, from_date, to_date):
	fields = [
		"name",
		"employee_number",
		"employee_name",
		"attendance_device_id",
		"company",
		"department",
		"designation",
		"branch",
		"date_of_joining",
		"relieving_date",
		"holiday_list",
		"default_shift",
		"custom_need_check",
		"custom_shift_group",
		"custom_working_schedule_type",
	]
	db_filters = {"status": "Active", "company": filters.company}
	if filters.get("department"):
		db_filters["department"] = filters.department
	if filters.get("branch"):
		db_filters["branch"] = filters.branch
	if filters.get("employee"):
		db_filters["name"] = filters.employee

	rows = frappe.get_list(
		"Employee",
		filters=db_filters,
		fields=fields,
		order_by="employee_name asc, name asc",
		limit_page_length=0,
	)
	return [
		row
		for row in rows
		if (not row.date_of_joining or getdate(row.date_of_joining) <= to_date)
		and (not row.relieving_date or getdate(row.relieving_date) >= from_date)
	]


def _apply_group_filters(employees, windows, filters, to_date):
	result = []
	for employee in employees:
		section, subgroup = _employee_group(employee, windows, to_date)
		if filters.get("area") and section != filters.area:
			continue
		if filters.get("shift_group") and subgroup != filters.shift_group:
			continue
		result.append(employee)
	return result


def _employee_group(employee, windows, to_date):
	window = windows.get((employee.name, to_date))
	shift_group = (window and window.get("shift_group")) or employee.get(
		"custom_shift_group"
	)
	if shift_group:
		return "Xưởng", shift_group
	if employee.get("custom_working_schedule_type") == "Theo kíp":
		return "Xưởng", "Chưa xếp kíp"

	department = _short_department(employee.department)
	if _normalize_text(department) in OFFICE_DEPARTMENTS:
		return "Văn phòng", ""
	return "HC", department or "Chưa có phòng ban"


def _combine_checkins(assigned, unplanned, windows, from_date, to_date):
	"""Gộp log theo ngày công, ưu tiên ca đã xếp để xử lý ca qua đêm."""
	combined = defaultdict(list)
	for key, logs in assigned.items():
		if from_date <= key[1] <= to_date:
			combined[key].extend(logs)

	for (_employee, calendar_date), logs in unplanned.items():
		for log in logs:
			log_time = get_datetime(log.time)
			target_date = calendar_date
			if log.shift_start:
				stored_date = getdate(log.shift_start)
				stored_window = windows.get((log.employee, stored_date))
				if (
					stored_window
					and not stored_window.is_off
					and (not log.shift or log.shift == stored_window.shift_type)
					and abs(log_time - stored_window.start_datetime) <= timedelta(hours=30)
				):
					target_date = stored_date
			if from_date <= target_date <= to_date:
				combined[(log.employee, target_date)].append(log)

	duplicate_map = defaultdict(list)
	for key, logs in combined.items():
		unique = {log.name: log for log in logs}
		combined[key], duplicate_map[key] = _deduplicate_logs(
			sorted(unique.values(), key=lambda log: get_datetime(log.time))
		)
	return combined, duplicate_map


def _deduplicate_logs(logs):
	"""Bỏ lượt quẹt lặp gần nhau của cùng trạng thái xếp ca.

	Hai lượt ra/vào thực sự ở ranh giới hai ca có thể cũng rất gần
	nhau. Vì vậy chỉ gộp khi cả hai cùng là off-shift hoặc cùng
	một shift_start; không gộp mù quáng theo khoảng thời gian.
	"""
	kept = []
	duplicates = []
	for log in logs:
		if not kept:
			kept.append(log)
			continue
		previous = kept[-1]
		delta = get_datetime(log.time) - get_datetime(previous.time)
		same_assignment = bool(
			(cint(log.offshift) and cint(previous.offshift))
			or (
				log.shift_start
				and previous.shift_start
				and get_datetime(log.shift_start) == get_datetime(previous.shift_start)
			)
		)
		if delta <= timedelta(minutes=DUPLICATE_PUNCH_MINUTES) and same_assignment:
			duplicates.append(log)
			continue
		kept.append(log)
	return kept, duplicates


def _make_detail_row(
	employee,
	work_date,
	logs,
	*,
	duplicate_logs,
	section,
	subgroup,
	sequence,
	company_name,
	from_date,
	to_date,
):
	visible_logs = list(logs[:4])
	# File chấm công mẫu chỉ thể hiện HH:mm, do đó phép tính cũng phải
	# dùng đúng độ chính xác đến phút. Nếu giữ giây từ máy chấm công,
	# người dùng sẽ không thể tính lại Tổng giờ từ bốn cột Vào/Ra.
	punch_times = [_truncate_to_minute(log.time) for log in visible_logs]
	while len(punch_times) < 4:
		punch_times.append(None)

	total_minutes = 0
	for start_index in (0, 2):
		start_time = punch_times[start_index]
		end_time = punch_times[start_index + 1]
		if start_time and end_time and end_time >= start_time:
			total_minutes += int((end_time - start_time).total_seconds() // 60)

	# Làm tròn HALF_UP giống cách HR đọc file Excel:
	# Tổng giờ = tổng phút / 60; Ngày công = Tổng giờ đã làm tròn / 8.
	total_hours_decimal = (
		Decimal(total_minutes) / HOURS_PER_MINUTE
	).quantize(DISPLAY_PRECISION, rounding=ROUND_HALF_UP)
	workdays_decimal = (total_hours_decimal / STANDARD_WORKDAY_HOURS).quantize(
		DISPLAY_PRECISION, rounding=ROUND_HALF_UP
	)
	total_hours = float(total_hours_decimal)
	workdays = float(workdays_decimal)
	extra_logs = list(logs[4:])
	display_department = (
		"Văn phòng" if section == "Văn phòng" else subgroup
	)
	return frappe._dict(
		stt=sequence,
		employee=employee.name,
		employee_code=(
			employee.employee_number or employee.attendance_device_id or employee.name
		),
		employee_name=employee.employee_name,
		display_department=display_department,
		department=employee.department,
		designation=employee.designation,
		work_date=work_date.isoformat(),
		work_date_display=work_date.strftime("%d/%m/%Y"),
		weekday_label=_weekday_label(work_date),
		in_1=_format_time(punch_times[0]),
		out_1=_format_time(punch_times[1]),
		in_2=_format_time(punch_times[2]),
		out_2=_format_time(punch_times[3]),
		total_hours=total_hours,
		workdays=workdays,
		tc1=0.0,
		tc2=0.0,
		tc3=0.0,
		grand_total=total_hours,
		section=section,
		subgroup=subgroup,
		company_name=company_name,
		from_date=from_date.isoformat(),
		to_date=to_date.isoformat(),
		punch_count=len(logs),
		extra_punch_count=len(extra_logs),
		extra_punches=", ".join(_format_time(get_datetime(log.time)) for log in extra_logs),
		duplicate_punch_count=len(duplicate_logs),
		duplicate_punches=", ".join(
			_format_time(get_datetime(log.time)) for log in duplicate_logs
		),
		checkin_names=", ".join(log.name for log in logs),
	)


def _truncate_to_minute(value):
	return get_datetime(value).replace(second=0, microsecond=0)


def _make_workbook(context):
	workbook = Workbook()
	worksheet = workbook.active
	worksheet.title = "Chi tiết"
	worksheet.sheet_view.showGridLines = False
	worksheet.freeze_panes = "A4"
	worksheet.page_setup.orientation = "landscape"
	worksheet.page_setup.fitToWidth = 1
	worksheet.sheet_properties.pageSetUpPr.fitToPage = True

	for column_index, (_fieldname, _label, width) in enumerate(HEADERS, start=1):
		worksheet.column_dimensions[_excel_column(column_index)].width = width

	last_column = len(HEADERS)
	worksheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_column)
	worksheet.cell(1, 1, "CHI TIẾT CHẤM CÔNG KHÔNG THEO CA")
	worksheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_column)
	worksheet.cell(
		2,
		1,
		f"Từ ngày {getdate(context.from_date).strftime('%d/%m/%Y')} "
		f"đến ngày {getdate(context.to_date).strftime('%d/%m/%Y')}",
	)
	for row_index in (1, 2):
		cell = worksheet.cell(row_index, 1)
		cell.font = Font(name="Arial", size=12, bold=True)
		cell.alignment = Alignment(horizontal="center", vertical="center")

	header_fill = PatternFill("solid", fgColor="F2F2F2")
	group_fill = PatternFill("solid", fgColor="D9D9D9")
	thin = Side(style="thin", color="000000")
	border = Border(left=thin, right=thin, top=thin, bottom=thin)
	for column_index, (_fieldname, label, _width) in enumerate(HEADERS, start=1):
		cell = worksheet.cell(3, column_index, label)
		cell.font = Font(name="Arial", size=10, bold=True)
		cell.fill = header_fill
		cell.alignment = Alignment(horizontal="center", vertical="center")
		cell.border = border

	current_row = 4
	grouped = _group_rows(context.rows)
	if context.rows:
		current_row = _append_group_row(
			worksheet,
			current_row,
			f"{context.company_name} ({context.employee_count})",
			last_column,
			group_fill,
			border,
		)

	for section, section_data in grouped.items():
		current_row = _append_group_row(
			worksheet,
			current_row,
			f"{section} ({section_data['employee_count']})",
			last_column,
			group_fill,
			border,
		)
		for subgroup, subgroup_data in section_data["subgroups"].items():
			if subgroup:
				current_row = _append_group_row(
					worksheet,
					current_row,
					f"     {subgroup} ({subgroup_data['employee_count']})",
					last_column,
					group_fill,
					border,
				)
			for row in subgroup_data["rows"]:
				values = [
					row.stt,
					row.employee_code,
					row.employee_name,
					row.display_department,
					row.designation,
					getdate(row.work_date),
					row.weekday_label,
					row.in_1,
					row.out_1,
					row.in_2,
					row.out_2,
					row.total_hours,
					row.workdays,
					row.tc1,
					row.tc2,
					row.tc3,
					row.grand_total,
				]
				for column_index, value in enumerate(values, start=1):
					cell = worksheet.cell(current_row, column_index, value)
					cell.font = Font(name="Arial", size=10)
					cell.alignment = Alignment(horizontal="center", vertical="center")
					cell.border = border
				if row.extra_punch_count:
					worksheet.cell(current_row, 11).comment = Comment(
						f"Còn {row.extra_punch_count} lượt chấm: {row.extra_punches}",
						"Vinatex HR",
					)
				if row.duplicate_punch_count:
					comment_text = (
						f"Đã loại {row.duplicate_punch_count} lượt chấm trùng trong "
						f"{DUPLICATE_PUNCH_MINUTES} phút: {row.duplicate_punches}"
					)
					comment_cell = worksheet.cell(current_row, 8)
					if comment_cell.comment:
						comment_text = f"{comment_cell.comment.text}\n{comment_text}"
					comment_cell.comment = Comment(comment_text, "Vinatex HR")
				worksheet.cell(current_row, 6).number_format = "dd/mm/yyyy"
				for column_index in range(12, 18):
					worksheet.cell(current_row, column_index).number_format = "0.000"
				current_row += 1

	worksheet.auto_filter.ref = f"A3:{_excel_column(last_column)}3"
	worksheet.print_title_rows = "1:3"
	return workbook


def _group_rows(rows):
	grouped = OrderedDict()
	for row in rows:
		section_data = grouped.setdefault(
			row.section,
			{"employees": set(), "employee_count": 0, "subgroups": OrderedDict()},
		)
		section_data["employees"].add(row.employee)
		subgroup_data = section_data["subgroups"].setdefault(
			row.subgroup,
			{"employees": set(), "employee_count": 0, "rows": []},
		)
		subgroup_data["employees"].add(row.employee)
		subgroup_data["rows"].append(row)
	for section_data in grouped.values():
		section_data["employee_count"] = len(section_data.pop("employees"))
		for subgroup_data in section_data["subgroups"].values():
			subgroup_data["employee_count"] = len(subgroup_data.pop("employees"))
	return grouped


def _append_group_row(worksheet, row_index, label, last_column, fill, border):
	worksheet.merge_cells(
		start_row=row_index,
		start_column=1,
		end_row=row_index,
		end_column=last_column,
	)
	cell = worksheet.cell(row_index, 1, label)
	cell.font = Font(name="Arial", size=10, bold=True)
	cell.fill = fill
	cell.alignment = Alignment(horizontal="left", vertical="center")
	# OpenPyXL cần gán style từng ô để viền của dòng merge được xuất đủ.
	for column_index in range(1, last_column + 1):
		merged_cell = worksheet.cell(row_index, column_index)
		merged_cell.fill = fill
		merged_cell.border = border
	return row_index + 1


def _validate_filters(filters):
	if not filters.get("company"):
		frappe.throw(_("Vui lòng chọn Công ty."))
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("Vui lòng chọn Từ ngày và Đến ngày."))
	from_date, to_date = getdate(filters.from_date), getdate(filters.to_date)
	if from_date > to_date:
		frappe.throw(_("Từ ngày không được sau Đến ngày."))
	if (to_date - from_date).days + 1 > MAX_REPORT_DAYS:
		frappe.throw(
			_("Báo cáo chỉ cho phép tối đa {0} ngày mỗi lần.").format(
				MAX_REPORT_DAYS
			)
		)
	return from_date, to_date


def _validate_access():
	if frappe.session.user == "Administrator":
		return
	if not ALLOWED_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("Bạn không có quyền xem báo cáo chấm công này."), frappe.PermissionError)


def _parse_filters(filters):
	if not filters:
		return {}
	if isinstance(filters, str):
		try:
			return json.loads(filters)
		except ValueError:
			frappe.throw(_("Bộ lọc xuất Excel không hợp lệ."))
	return dict(filters)


def _date_range(from_date, to_date):
	current = from_date
	while current <= to_date:
		yield current
		current += timedelta(days=1)


def _weekday_label(work_date):
	return "CN" if work_date.weekday() == 6 else f"T.{work_date.weekday() + 2}"


def _format_time(value):
	return value.strftime("%H:%M") if value else ""


def _short_department(department):
	if not department:
		return ""
	return department.rsplit(" - ", 1)[0].strip()


def _normalize_text(value):
	text = unicodedata.normalize("NFD", (value or "").strip().lower())
	text = "".join(character for character in text if unicodedata.category(character) != "Mn")
	return text.replace("đ", "d")


def _section_order(section):
	return {"HC": 0, "Văn phòng": 1, "Xưởng": 2}.get(section, 99)


def _natural_key(value):
	return [
		int(part) if part.isdigit() else _normalize_text(part)
		for part in re.split(r"(\d+)", value or "")
	]


def _excel_column(column_index):
	result = ""
	while column_index:
		column_index, remainder = divmod(column_index - 1, 26)
		result = chr(65 + remainder) + result
	return result
