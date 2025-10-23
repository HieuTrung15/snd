import io
from datetime import date, datetime, time, timedelta
from frappe import _
import frappe
from frappe.utils import cint, getdate, flt
from calendar import monthrange
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from frappe.utils.file_manager import save_file

STATUS_CODE = {
	"CHƯA VÀO LÀM": "CV",     # Trước ngày vào làm
	"NGHỈ LỄ": "L",           # Nghỉ lễ theo Holiday List (không tính weekend)
	"CUỐI TUẦN": "T",        # Thứ 7/CN
	"ĐI LÀM": "X",            # Đi làm
	"VẮNG MẶT": "V",          # Vắng mặt
	"QUÊN CHẤM CÔNG": "O",  # Quên chấm công,
	"NGHỈ PHÉP": "P",
	"NGHỈ VIỆC RIÊNG KHÔNG HƯỞNG LƯƠNG": "Ro",
	"NGHỈ CÓ HƯỞNG LƯƠNG, CHẾ ĐỘ": "CĐ",
	"NGHỈ HƯỞNG CHẾ ĐỘ BHXH": "BH",
	"VẮNG MẶT TẠI TRỤ SỞ CÔNG TY CÓ LÝ DO CÔNG VIỆC": "CT",
}

def execute(filters):
	start_date = getdate(filters.get("from_date"))
	end_date = getdate(filters.get("to_date"))
	days = list(_daterange(start_date, end_date))
	cols = _columns_pivot(days)

	emps = _get_employees(filters, start_date, end_date)
	if not emps:
		return cols, []

	# maps
	holi_map = _holiday_map(emps, filters["company"], start_date, end_date)  # chỉ ngày lễ (loại weekend)
	att_map  = _attendance_map(emps, start_date, end_date)                    # ƯU TIÊN dùng trước leave/checkin
	leave_map = _leave_map(emps, start_date, end_date)
	checkin_map = _checkin_map(emps, start_date, end_date)
	shift_map = _shift_map(emps, days) if cint(filters.get("use_shift_plan")) else {}

	# Defaults nếu không dùng ca
	s_start = _parse_time(filters.get("shift_start") or "08:15:00")
	s_end   = _parse_time(filters.get("shift_end") or "17:00:00")

	out = []
	for emp in emps:
		emp_code = emp["name"]
		manual_flag = cint(emp.get("custom_need_check"))
		doj = getdate(emp.get("date_of_joining")) if emp.get("date_of_joining") else date.min

		row = {
			"employee": emp_code,
			"employee_name": emp["employee_name"],
			"department": emp.get("department"),
			"designation": emp.get("designation"),
			# totals
			"tot_present": 0,
			"tot_leave": 0,
			"tot_holiday": 0,
			"tot_weekend": 0,
			"tot_absent": 0,
			"tot_late": 0,
			"tot_miss": 0,
			"tot_not_joined": 0,
		}

		for d in days:
			key = f"d{d.day:02d}"
			d_date = getdate(d)
			# 1) DOJ
			if d_date < doj:
				row[key] = STATUS_CODE["CHƯA VÀO LÀM"]
				row["tot_not_joined"] += 1
				continue

			# 2) Holiday (ưu tiên hơn weekend & attendance)
			if (emp_code, d_date) in holi_map:
				row[key] = STATUS_CODE["NGHỈ LỄ"]
				row["tot_holiday"] += 1
				continue

			# 3) Cuối tuần
			if _is_weekend(d_date):
				row[key] = STATUS_CODE["CUỐI TUẦN"]
				row["tot_weekend"] += 1
				continue

			# 4) Attendance (ƯU TIÊN trước Leave/Checkin)
			att = att_map.get((emp_code, d_date))
			if att:
				st = (att.get("status") or "").strip()
				if st in ("Present", "Work From Home"):
					row[key] = STATUS_CODE["ĐI LÀM"]
					row["tot_present"] += 1
				elif st in ("On Leave",):
					row[key] = STATUS_CODE["NGHỈ PHÉP"]
					row["tot_leave"] += 1
				elif st in ("Half Day",):
					row[key] = STATUS_CODE["NGHỈ NỬA NGÀY"]
					# nếu muốn cộng 0.5 ngày nghỉ: đổi tot_leave -> Float và cộng 0.5 ở đây
				elif st in ("Absent",):
					row[key] = STATUS_CODE["VẮNG MẶT"]
					row["tot_absent"] += 1
				else:
					# fallback nếu có trạng thái lạ: coi là vắng
					row[key] = STATUS_CODE["VẮNG MẶT"]
					row["tot_absent"] += 1
				continue

			# 5) Leave (fallback khi không có Attendance)
			lv = leave_map.get((emp_code, d_date))
			if lv:
				if lv.get("half_day"):
					row[key] = STATUS_CODE["NGHỈ NỬA NGÀY"]
				else:
					row[key] = STATUS_CODE["NGHỈ PHÉP"]
					row["tot_leave"] += 1
				continue

			# 6) Checkin (cuối cùng)
			chk = checkin_map.get((emp_code, d_date), {"first_in": None, "last_out": None, "cnt_in": 0, "cnt_out": 0})
			fi, lo, ci, co = chk["first_in"], chk["last_out"], chk["cnt_in"], chk["cnt_out"]

			if ci == 0 and co == 0:
				row[key] = STATUS_CODE["VẮNG MẶT"]
				row["tot_absent"] += 1
				continue

			# Khung giờ
			if (emp_code, d_date) in shift_map:
				sstart, send = shift_map[(emp_code, d_date)]
			else:
				sstart, send = s_start, s_end

			late_mins = _mins_after(fi.time(), sstart) if fi else None
			if ci > 0 and co > 0:
				row[key] = STATUS_CODE["ĐI LÀM"]
				row["tot_present"] += 1
				if late_mins and late_mins > 0:
					row["tot_late"] += 1
			else:
				row[key] = STATUS_CODE["QUÊN CHẤM CÔNG"]
				row["tot_miss"] += 1

		if manual_flag:
			for fld in ("tot_present", "tot_leave", "tot_holiday", "tot_weekend", "tot_absent", "tot_late", "tot_miss", "tot_not_joined"):
				row[fld] = None

		out.append(row)

	# message = get_message() if not filters.summarized_view else ""
	return cols, out


def _columns_pivot(days):
	base = [
		{"fieldname": "employee", "label": "Mã NV", "fieldtype": "Link", "options": "Employee", "width": 100},
		{"fieldname": "employee_name", "label": "Tên NV", "fieldtype": "Data", "width": 150},
		{"fieldname": "department", "label": "Phòng ban", "fieldtype": "Link", "options": "Department", "width": 140},
		{"fieldname": "designation", "label": "Chức vụ", "fieldtype": "Data", "width": 140},
	]
	for d in days:
		base.append({
			"fieldname": f"d{d.day:02d}",
			"label": f"{d.day:02d}",
			"fieldtype": "Data",
			"width": 42,
		})
	base += [
		{"fieldname": "tot_present", "label": "Đi làm",  "fieldtype": "Int", "width": 100},
		{"fieldname": "tot_leave",   "label": "Nghỉ phép",  "fieldtype": "Int", "width": 100},
		{"fieldname": "tot_holiday", "label": "Nghỉ Lễ",  "fieldtype": "Int", "width": 100},
		{"fieldname": "tot_weekend", "label": "Công tác", "fieldtype": "Int", "width": 100},
		{"fieldname": "tot_absent",  "label": "Vắng",  "fieldtype": "Int", "width": 100},
		{"fieldname": "tot_miss",    "label": "Quên chấm công","fieldtype": "Int", "width": 100},
	]
	return base

# ====== helpers giữ nguyên, chỉ bổ sung _attendance_map và chỉnh _holiday_map lọc weekend ======
def _month_bounds(year, month):
	sd = date(year, month, 1)
	if month == 12:
		ed = date(year, 12, 31)
	else:
		ed = date(year, month + 1, 1) - timedelta(days=1)
	return sd, ed

def _daterange(sd, ed):
	d = sd
	while d <= ed:
		yield d
		d += timedelta(days=1)

def _parse_time(tstr):
	if isinstance(tstr, time):
		return tstr
	hh, mm, ss = [int(x) for x in str(tstr).split(":")]
	return time(hh, mm, ss)

def _get_employees(filters, start_date, end_date):
	conds = ["company=%s", "status='Active'"]
	vals = [filters["company"]]
	conds.append("(ifnull(relieving_date,'2099-12-31') >= %s)")
	vals.append(start_date)
	conds.append("(ifnull(date_of_joining,'1900-01-01') <= %s)")
	vals.append(end_date)
	if filters.get("department"):
		conds.append("department=%s"); vals.append(filters["department"])
	if filters.get("employee"):
		conds.append("name=%s"); vals.append(filters["employee"])
	sql = f"""
		SELECT
			name,
			employee_name,
			department,
			designation,
			custom_designation_group,
			custom_need_check,
			date_of_joining,
			relieving_date,
			holiday_list
		FROM `tabEmployee`
		WHERE {" AND ".join(conds)}
		AND (
			custom_need_check = 1
			OR COALESCE(attendance_device_id, '') != ''
		)
		ORDER BY
			CASE
				WHEN designation = 'Tổng Giám đốc Tập đoàn' THEN -2
				WHEN custom_need_check = 1 THEN -1
				WHEN custom_designation_group = 'Người quản lý' THEN 0
				WHEN custom_designation_group = 'Lãnh đạo cấp trung' THEN 2
				WHEN COALESCE(custom_designation_group, '') = '' THEN 99
				ELSE 2
			END,
			department,
			employee_name
	"""
	return frappe.db.sql(sql, vals, as_dict=True)

def _holiday_map(emps, company, start_date, end_date):
	"""Trả LỄ, bỏ weekend (weekly_off=1) để weekend do _is_weekend quyết định."""
	out = {}
	comp_hl = frappe.db.get_value("Company", company, "default_holiday_list")
	cache = {}
	def fetch_days(holiday_list):
		if not holiday_list: return []
		if holiday_list in cache: return cache[holiday_list]
		rows = frappe.db.sql("""
			SELECT holiday_date, description, COALESCE(weekly_off, 0) AS weekly_off
			FROM `tabHoliday`
			WHERE parent=%s AND holiday_date BETWEEN %s AND %s
		""", (holiday_list, start_date, end_date), as_dict=True)
		cache[holiday_list] = rows
		return rows
	for e in emps:
		hl = e.get("holiday_list") or comp_hl
		for r in fetch_days(hl):
			d = getdate(r.holiday_date)
			if cint(r.weekly_off) == 1:
				continue  # để weekend hiển thị CT riêng
			out[(e["name"], d)] = r.description or "Holiday"
	return out

def _attendance_map(emps, start_date, end_date):
	"""Map (emp, day) -> Attendance record fields cần dùng."""
	out = {}
	emp_list = [e["name"] for e in emps]
	if not emp_list:
		return out
	rows = frappe.db.sql("""
		SELECT employee, attendance_date, status, leave_type
		FROM `tabAttendance`
		WHERE docstatus=1
		  AND employee IN %(emps)s
		  AND attendance_date BETWEEN %(sd)s AND %(ed)s
	""", {"emps": tuple(emp_list), "sd": start_date, "ed": end_date}, as_dict=True)
	for r in rows:
		out[(r.employee, getdate(r.attendance_date))] = {
			"status": r.status,
			"leave_type": r.leave_type,
		}
	return out

def _leave_map(emps, start_date, end_date):
	out = {}
	emp_list = [e["name"] for e in emps]
	if not emp_list: return out
	rows = frappe.db.sql("""
		SELECT name, employee, from_date, to_date, half_day, half_day_date, leave_type, custom_leave_group
		FROM `tabLeave Application`
		WHERE docstatus=1 AND status='Approved'
		  AND employee IN %(emps)s
		  AND to_date >= %(sd)s AND from_date <= %(ed)s
	""", {"emps": tuple(emp_list), "sd": start_date, "ed": end_date}, as_dict=True)
	for r in rows:
		cur = max(getdate(r.from_date), start_date)
		last = min(getdate(r.to_date), end_date)
		while cur <= last:
			out[(r.employee, cur)] = {
				"leave_type": r.leave_type,
				"half_day": bool(r.half_day and getdate(r.half_day_date) == cur),
				"leave_name": r.name,
				"leave_group": r.custom_leave_group,
			}
			cur += timedelta(days=1)
	return out

def _checkin_map(emps, start_date, end_date):
	out = {}
	emp_list = [e["name"] for e in emps]
	if not emp_list: return out
	rows = frappe.db.sql("""
		SELECT employee, DATE(time) as d,
			   MIN(CASE WHEN log_type='IN'  THEN time END)  as first_in,
			   MAX(CASE WHEN log_type='OUT' THEN time END)  as last_out,
			   SUM(CASE WHEN log_type='IN'  THEN 1 ELSE 0 END)  as cnt_in,
			   SUM(CASE WHEN log_type='OUT' THEN 1 ELSE 0 END)  as cnt_out
		FROM `tabEmployee Checkin`
		WHERE employee IN %(emps)s
		  AND time BETWEEN %(sd)s AND %(ed2)s
		GROUP BY employee, DATE(time)
	""", {
		"emps": tuple(emp_list),
		"sd": datetime.combine(start_date, time.min),
		"ed2": datetime.combine(end_date, time.max)
	}, as_dict=True)
	for r in rows:
		out[(r.employee, getdate(r.d))] = {
			"first_in": r.first_in,
			"last_out": r.last_out,
			"cnt_in": int(r.cnt_in or 0),
			"cnt_out": int(r.cnt_out or 0)
		}
	return out

def _shift_map(emps, days):
	out = {}
	emp_list = [e["name"] for e in emps]
	if not emp_list: return out
	sd = min(days); ed = max(days)
	rows = frappe.db.sql("""
		SELECT sa.employee, sa.start_date, sa.end_date,
			   st.name as shift_type, st.start_time, st.end_time
		FROM `tabShift Assignment` sa
		JOIN `tabShift Type` st ON st.name=sa.shift_type
		WHERE sa.employee IN %(emps)s
		  AND sa.docstatus=1
		  AND sa.end_date >= %(sd)s AND sa.start_date <= %(ed)s
	""", {"emps": tuple(emp_list), "sd": sd, "ed": ed}, as_dict=True)
	for r in rows:
		cur = max(getdate(r.start_date), sd)
		last = min(getdate(r.end_date), ed)
		s_t = _parse_time(str(r.start_time)); e_t = _parse_time(str(r.end_time))
		while cur <= last:
			out[(r.employee, cur)] = (s_t, e_t)
			cur += timedelta(days=1)
	return out

def _mins_after(actual: time, ref: time):
	a = datetime.combine(date.today(), actual)
	r = datetime.combine(date.today(), ref)
	return max(0, int((a - r).total_seconds() // 60))

def _mins_before(actual: time, ref: time):
	a = datetime.combine(date.today(), actual)
	r = datetime.combine(date.today(), ref)
	return max(0, int((r - a).total_seconds() // 60))

def _is_weekend(d: date) -> bool:
	return d.weekday() >= 5


def _leave_type_group_map():
	"""Trả về map {leave_type -> leave_group} phục vụ phân loại ngày nghỉ."""
	rows = frappe.db.sql("""
		SELECT name, custom_leave_group
		FROM `tabLeave Type`
	""", as_dict=True)
	out = {}
	for r in rows:
		out[r.name] = r.custom_leave_group
	return out


def _is_remote_leave(name: str) -> bool:
	text = (name or "").lower()
	keywords = ["từ xa", "tu xa", "remote", "work from home", "wfh"]
	return any(k in text for k in keywords)


def _is_business_trip_leave(name: str) -> bool:
	text = (name or "").lower()
	keywords = [
		"công tác",
		"cong tac",
		"đi học",
		"di hoc",
		"đi họp",
		"di hop",
		"business trip",
		"work trip",
		"đi công tác",
	]
	return any(k in text for k in keywords)


def _categorize_leave(leave_type: str, leave_group: str) -> str:
	group = (leave_group or "").lower()
	if group:
		if "không hưởng lương" in group or "khong huong luong" in group:
			return "unpaid"
		if "nghỉ phép" in group or "nghi phep" in group:
			return "paid_leave"
		if "bhxh" in group or "chế độ" in group or "che do" in group:
			return "regime"
		if "vắng mặt" in group or "vang mat" in group:
			if leave_type and _is_remote_leave(leave_type):
				return "remote"
			return "business_trip"
		if "nghỉ theo lịch" in group or "nghi theo lich" in group:
			return "holiday"
	if leave_type:
		if _is_remote_leave(leave_type):
			return "remote"
		if _is_business_trip_leave(leave_type):
			return "business_trip"
		lower_type = leave_type.lower()
		if any(k in lower_type for k in ["không lương", "khong luong", "unpaid"]):
			return "unpaid"
		if any(k in lower_type for k in ["ốm", "om", "thai", "dưỡng", "duong", "bhxh", "chế độ", "che do", "khám thai", "kham thai"]):
			return "regime"
	return "paid_leave"


def _add_category_units(metrics: dict, category: str, units: float):
	if units <= 0:
		return
	if category == "paid_leave":
		metrics["paid_leave"] += units
		metrics["paid"] += units
	elif category == "regime":
		metrics["regime"] += units
		metrics["paid"] += units
	elif category == "business_trip":
		metrics["business_trip"] += units
		metrics["paid"] += units
	elif category == "remote":
		metrics["remote"] += units
		metrics["paid"] += units
	elif category == "holiday":
		metrics["holiday"] += units
		metrics["paid"] += units
	elif category == "unpaid":
		metrics["unpaid"] += units
	else:
		metrics["paid_leave"] += units
		metrics["paid"] += units


def _compute_employee_metrics(emp, days, holi_map, att_map, leave_map, checkin_map, leave_type_groups):
	emp_code = emp["name"]
	doj = getdate(emp.get("date_of_joining")) if emp.get("date_of_joining") else date.min
	skip_manual = cint(emp.get("custom_need_check"))
	metrics = {
		"paid": 0.0,
		"actual": 0.0,
		"holiday": 0.0,
		"business_trip": 0.0,
		"paid_leave": 0.0,
		"regime": 0.0,
		"unpaid": 0.0,
		"remote": 0.0,
		"forget": 0.0,
	}

	if skip_manual:
		return metrics, True

	for d in days:
		if d < doj:
			continue

		key = (emp_code, d)

		if key in holi_map:
			metrics["holiday"] += 1.0
			metrics["paid"] += 1.0
			continue

		weekday = d.weekday()
		att = att_map.get(key)
		if att:
			status = (att.get("status") or "").strip()
			leave_type = att.get("leave_type")
			leave_group = leave_type_groups.get(leave_type)
			units = 1.0
			if status == "Half Day":
				units = 0.5
				metrics["actual"] += units if weekday < 5 else 0
				metrics["paid"] += units
				continue
			if status in ("Present",):
				if weekday < 5:
					metrics["actual"] += units
				metrics["paid"] += units
				continue
			if status == "Work From Home":
				metrics["remote"] += units
				metrics["paid"] += units
				continue
			if status == "Work Trip":
				metrics["business_trip"] += units
				metrics["paid"] += units
				continue
			if status == "On Leave":
				category = _categorize_leave(leave_type, leave_group)
				_add_category_units(metrics, category, units)
				continue
			if status == "Absent":
				continue

		leave = leave_map.get(key)
		if leave:
			units = 0.5 if leave.get("half_day") else 1.0
			leave_type = leave.get("leave_type")
			leave_group = leave.get("leave_group") or leave_type_groups.get(leave_type)
			category = _categorize_leave(leave_type, leave_group)
			_add_category_units(metrics, category, units)
			continue

		chk = checkin_map.get(key)
		if chk:
			ci = int(chk.get("cnt_in") or 0)
			co = int(chk.get("cnt_out") or 0)
			if ci == 0 and co == 0:
				continue
			if ci > 0 and co > 0:
				if weekday < 5:
					metrics["actual"] += 1.0
				metrics["paid"] += 1.0
			else:
				metrics["forget"] += 1.0
			continue

	return metrics, False


def _build_summary_rows(employees, days, holi_map, att_map, leave_map, checkin_map, leave_type_groups):
	rows = []
	totals = {
		"paid_days": 0.0,
		"actual_days": 0.0,
		"holiday_days": 0.0,
		"business_trip_days": 0.0,
		"paid_leave_days": 0.0,
		"regime_days": 0.0,
		"unpaid_days": 0.0,
		"remote_days": 0.0,
		"forget_days": 0.0,
	}

	for emp in employees:
		metrics, skip_manual = _compute_employee_metrics(
			emp,
			days,
			holi_map,
			att_map,
			leave_map,
			checkin_map,
			leave_type_groups,
		)
		row = {
			"employee": emp["name"],
			"employee_name": emp["employee_name"],
			"department": emp.get("department"),
			"designation": emp.get("designation"),
			"paid_days": "" if skip_manual else flt(metrics["paid"], 4),
			"actual_days": "" if skip_manual else flt(metrics["actual"], 4),
			"holiday_days": "" if skip_manual else flt(metrics["holiday"], 4),
			"business_trip_days": "" if skip_manual else flt(metrics["business_trip"], 4),
			"paid_leave_days": "" if skip_manual else flt(metrics["paid_leave"], 4),
			"regime_days": "" if skip_manual else flt(metrics["regime"], 4),
			"unpaid_days": "" if skip_manual else flt(metrics["unpaid"], 4),
			"remote_days": "" if skip_manual else flt(metrics["remote"], 4),
			"forget_days": "" if skip_manual else flt(metrics["forget"], 4),
		}
		rows.append(row)
		if not skip_manual:
			for key in totals:
				totals[key] += row[key]

	return rows, totals


@frappe.whitelist()
def download_summary_xlsx(filters):
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)

	if not filters:
		filters = {}

	start_date = filters.get("from_date")
	end_date = filters.get("to_date")

	if not start_date or not end_date:
		frappe.throw(_("Vui lòng chọn khoảng thời gian."))

	start_date = getdate(start_date)
	end_date = getdate(end_date)

	company = filters.get("company")
	if not company:
		frappe.throw(_("Vui lòng chọn Công ty."))

	if end_date < start_date:
		frappe.throw(_("Đến ngày phải lớn hơn hoặc bằng Từ ngày."))

	days = list(_daterange(start_date, end_date))

	employees = _get_employees(filters, start_date, end_date)
	if not employees:
		frappe.throw(_("Không tìm thấy nhân viên phù hợp bộ lọc."))

	leave_type_groups = _leave_type_group_map()

	holi_map = _holiday_map(employees, company, start_date, end_date)
	att_map = _attendance_map(employees, start_date, end_date)
	leave_map = _leave_map(employees, start_date, end_date)
	checkin_map = _checkin_map(employees, start_date, end_date)

	summary_rows, totals = _build_summary_rows(
		employees, days, holi_map, att_map, leave_map, checkin_map, leave_type_groups
	)

	output = io.BytesIO()
	workbook = Workbook()
	sheet = workbook.active
	sheet.title = _("Tổng hợp")

	thin = Side(style="thin", color="000000")
	border = Border(left=thin, right=thin, top=thin, bottom=thin)

	header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
	text_alignment = Alignment(horizontal="left", vertical="center")
	center_alignment = Alignment(horizontal="center", vertical="center")
	total_alignment = Alignment(horizontal="right", vertical="center")
	number_format = "0.00"

	header_font = Font(bold=True)
	total_font = Font(bold=True)

	title_fill = PatternFill("solid", fgColor="EBF3FF")
	sub_header_fill = PatternFill("solid", fgColor="DCE6F1")
	total_fill = PatternFill("solid", fgColor="FFF2CC")

	sheet.row_dimensions[1].height = 26
	sheet.row_dimensions[2].height = 26

	column_widths = {
		"A": 5,
		"B": 28,
		"C": 22,
		"D": 20,
		"E": 16,
		"F": 16,
		"G": 16,
		"H": 16,
		"I": 16,
		"J": 16,
		"K": 16,
		"L": 16,
		"M": 16,
	}
	for col, width in column_widths.items():
		sheet.column_dimensions[col].width = width

	def write_header(r1, c1, r2, c2, value, fill=title_fill):
		sheet.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)
		for rr in range(r1, r2 + 1):
			for cc in range(c1, c2 + 1):
				cell = sheet.cell(row=rr, column=cc)
				if rr == r1 and cc == c1:
					cell.value = value
				cell.font = header_font
				cell.alignment = header_alignment
				cell.fill = fill
				cell.border = border

	write_header(1, 1, 2, 1, _("STT"))
	write_header(1, 2, 2, 2, _("Tên nhân viên"))
	write_header(1, 3, 2, 3, _("Phòng ban"))
	write_header(1, 4, 2, 4, _("Chức vụ"))
	write_header(1, 5, 2, 5, _("Số công hưởng lương"))
	write_header(1, 6, 2, 6, _("Số công thực tế (T2-T6)"))
	write_header(1, 7, 1, 10, _("Nghỉ có hưởng lương"))

	sub_headers = [
		(_("Nghỉ Lễ, Tết"), 7),
		(_("Công tác/ Đi học"), 8),
		(_("Nghỉ phép"), 9),
		(_("Chế độ"), 10),
	]
	for label, col in sub_headers:
		cell = sheet.cell(row=2, column=col, value=label)
		cell.font = header_font
		cell.alignment = header_alignment
		cell.fill = sub_header_fill
		cell.border = border

	write_header(1, 11, 2, 11, _("Nghỉ không lương/ Nghỉ ốm/TS"))
	write_header(1, 12, 2, 12, _("Làm việc Từ xa"))
	write_header(1, 13, 2, 13, _("Quên chấm công"))

	data_start_row = 3
	current_row = data_start_row

	for idx, row in enumerate(summary_rows, start=1):
		values = [
			idx,
			row["employee_name"],
			row.get("department") or "",
			row.get("designation") or "",
			row["paid_days"],
			row["actual_days"],
			row["holiday_days"],
			row["business_trip_days"],
			row["paid_leave_days"],
			row["regime_days"],
			row["unpaid_days"],
			row["remote_days"],
			row["forget_days"],
		]

		for col_idx, value in enumerate(values, start=1):
			cell = sheet.cell(row=current_row, column=col_idx, value=value)
			cell.border = border
			if col_idx == 1:
				cell.alignment = center_alignment
			elif col_idx in (4,):
				cell.alignment = text_alignment
			elif col_idx in (2, 3):
				cell.alignment = text_alignment
			else:
				cell.alignment = center_alignment
				cell.number_format = number_format if value != "" else "General"
		current_row += 1

	if summary_rows:
		sheet.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=4)
		label_cell = sheet.cell(row=current_row, column=1, value=_("Tổng"))
		label_cell.font = total_font
		label_cell.alignment = total_alignment
		label_cell.border = border
		label_cell.fill = total_fill

		total_values = [
			totals["paid_days"],
			totals["actual_days"],
			totals["holiday_days"],
			totals["business_trip_days"],
			totals["paid_leave_days"],
			totals["regime_days"],
			totals["unpaid_days"],
			totals["remote_days"],
			totals["forget_days"],
		]

		for offset, total_value in enumerate(total_values, start=0):
			col = 5 + offset
			cell = sheet.cell(row=current_row, column=col, value=flt(total_value, 4))
			cell.font = total_font
			cell.alignment = center_alignment
			cell.border = border
			cell.fill = total_fill
			cell.number_format = number_format

	sheet.freeze_panes = "A3"

	workbook.save(output)
	output.seek(0)

	filename = _("Tong_hop_cham_cong_{0}_{1}.xlsx").format(start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d"))
	file_doc = save_file(filename, output.getvalue(), None, None, is_private=1)
	return {"file_url": file_doc.file_url}


def get_message() -> str:
	message = ""
	colors = [
		"green", "red", "orange", "#914EE3", "#3187D8", "#878787", 
		"#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FECA57"
	]
	count = 0
	for status, abbr in STATUS_CODE.items():
		color = colors[count % len(colors)]  # Sử dụng modulo để tránh index out of range
		message += f"""
			<span style='border-left: 2px solid {color}; padding-right: 12px; padding-left: 5px; margin-right: 3px;'>
				{_(status)} - {abbr}
			</span>
		"""
		count += 1
	return message

def chart_data(rows):
	# Initialize aggregation dictionary
	agg = {
		"X": 0,    # Đi làm
		"P": 0,    # Nghỉ phép
		"L": 0,    # Nghỉ lễ
		"CT": 0,   # Cuối tuần
		"V": 0,    # Vắng mặt
		"QCC": 0,  # Quên chấm công
		"CV": 0,   # Chưa vào làm
		"Ro": 0,   # Nghỉ việc riêng không hưởng lương
		"CĐ": 0    # Nghỉ có hưởng lương, chế độ
	}
	
	# Aggregate data from rows
	for r in rows:
		agg["X"]   += flt(r.get("tot_present") or 0)
		agg["P"]   += flt(r.get("tot_leave") or 0)
		agg["L"]   += flt(r.get("tot_holiday") or 0)
		agg["CT"]  += flt(r.get("tot_weekend") or 0)
		agg["V"]   += flt(r.get("tot_absent") or 0)
		agg["QCC"] += flt(r.get("tot_miss") or 0)
		agg["CV"]  += flt(r.get("tot_not_joined") or 0)
		agg["Ro"]  += flt(r.get("tot_unpaid_leave") or 0)
		agg["CĐ"]  += flt(r.get("tot_paid_leave") or 0)
	
	# Return chart configuration
	labels = []
	values = []
	
	# Create labels and values from STATUS_CODE dynamically
	for status, abbr in STATUS_CODE.items():
		if abbr in agg and agg[abbr] > 0:  # Only include non-zero values
			labels.append(f"{status} ({abbr})")
			values.append(agg[abbr])
	
	return {
		"data": {
			"labels": labels,
			"datasets": [
				{
					"name": "Số ngày",
					"values": values
				}
			]
		},
		"type": "donut",
	}
