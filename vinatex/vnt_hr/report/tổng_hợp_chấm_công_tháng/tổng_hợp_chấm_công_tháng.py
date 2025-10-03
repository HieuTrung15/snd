from datetime import date, datetime, time, timedelta
from frappe import _
import frappe
from frappe.utils import cint, cstr, getdate
from calendar import monthrange

STATUS_CODE = {
	"CHƯA VÀO LÀM": "CV",    # Trước ngày vào làm
	"NGHỈ LỄ": "L",        # Nghỉ lễ theo Holiday List
	"CUỔI TUẦN": "CT",       # Cuối tuần (thứ 7/CN)
	"NGHỈ PHÉP": "P",          # Nghỉ phép
	"NGHỈ NỬA NGÀY": "0.5L",  # Nghỉ 0.5 ngày
	"ĐI LÀM": "X",        # Đi làm
	"VẮNG MẶT": "V",         # Vắng mặt
	"QUÊN CHẤM CÔNG": "QCC",     # Quên chấm công
}

def execute(filters):
	if not filters.get("month") or not filters.get("year") or not filters.get("company"):
		frappe.throw("Vui lòng chọn Company, Month, Year")

	start_date, end_date = _month_bounds(int(filters.year), int(filters.month))
	days = list(_daterange(start_date, end_date))
	cols = _columns_pivot(days)

	emps = _get_employees(filters, start_date, end_date)
	if not emps:
		return cols, []

	# maps
	holi_map = _holiday_map(emps, filters["company"], start_date, end_date)
	leave_map = _leave_map(emps, start_date, end_date)
	checkin_map = _checkin_map(emps, start_date, end_date)
	shift_map = _shift_map(emps, days) if cint(filters.get("use_shift_plan")) else {}

	# Defaults if no shift plan
	s_start = _parse_time(filters.get("shift_start") or "08:00:00")
	s_end   = _parse_time(filters.get("shift_end") or "17:00:00")

	out = []
	for emp in emps:
		emp_code = emp["name"]
		doj = getdate(emp.get("date_of_joining")) if emp.get("date_of_joining") else date.min

		# init row
		row = {
			"employee": emp_code,
			"employee_name": emp["employee_name"],
			"department": emp.get("department"),
			# totals
			"tot_present": 0,
			"tot_leave": 0,
			"tot_holiday": 0,
			"tot_weekend": 0,     # <-- tổng cuối tuần
			"tot_absent": 0,
			"tot_late": 0,
			"tot_miss": 0,
		}

		for d in days:
			key = f"d{d.day:02d}"  # d01..d31

			# 1) DOJ
			if d < doj:
				row[key] = STATUS_CODE["CHƯA VÀO LÀM"]
				continue

			# 2) Holiday (ưu tiên hơn cuối tuần nếu trùng)
			if (emp_code, d) in holi_map:
				row[key] = STATUS_CODE["NGHỈ LỄ"]
				row["tot_holiday"] += 1
				continue

			# 3) Cuối tuần (Thứ 7/CN)
			if _is_weekend(d):
				row[key] = STATUS_CODE["CUỐI TUẦN"]
				row["tot_weekend"] += 1
				continue

			# 4) Leave
			lv = leave_map.get((emp_code, d))
			if lv:
				if lv.get("half_day"):
					row[key] = STATUS_CODE["NGHỈ NỬA NGÀY"]
				else:
					row[key] = STATUS_CODE["NGHỈ PHÉP"]
					row["tot_leave"] += 1
				continue

			# 5) Checkin
			chk = checkin_map.get((emp_code, d), {"first_in": None, "last_out": None, "cnt_in": 0, "cnt_out": 0})
			fi, lo, ci, co = chk["first_in"], chk["last_out"], chk["cnt_in"], chk["cnt_out"]

			# vắng
			if ci == 0 and co == 0:
				row[key] = STATUS_CODE["VẮNG MẶT"]
				row["tot_absent"] += 1
				continue

			# khung giờ
			if (emp_code, d) in shift_map:
				sstart, send = shift_map[(emp_code, d)]
			else:
				sstart, send = s_start, s_end

			late_mins = _mins_after(fi.time(), sstart) if fi else None
			# work đầy đủ
			if ci > 0 and co > 0:
				row[key] = STATUS_CODE["ĐI LÀM"]
				row["tot_present"] += 1
				if late_mins and late_mins > 0:
					row["tot_late"] += 1
			else:
				# miss punch
				row[key] = STATUS_CODE["QUÊN CHẤM CÔNG"]
				row["tot_miss"] += 1

		out.append(row)
	message = get_message() if not filters.summarized_view else ""
	chart = chart_data(out)
	return cols, out, message, chart


def _columns_pivot(days):
	base = [
		{"fieldname": "employee", "label": "Mã NV", "fieldtype": "Link", "options": "Employee", "width": 90},
		{"fieldname": "employee_name", "label": "Tên NV", "fieldtype": "Data", "width": 150},
		{"fieldname": "department", "label": "Phòng ban", "fieldtype": "Link", "options": "Department", "width": 140},
	]
	# ngày theo chiều ngang
	for d in days:
		base.append({
			"fieldname": f"d{d.day:02d}",
			"label": f"{d.day:02d}",
			"fieldtype": "Data",
			"width": 100,   # nhỏ để nhìn hết tháng (có thể giảm 56-72)
		})
	# totals
	base += [
		{"fieldname": "tot_present", "label": "X",  "fieldtype": "Int", "width": 80},
		{"fieldname": "tot_leave",   "label": "P",  "fieldtype": "Int", "width": 80},
		{"fieldname": "tot_holiday", "label": "L",  "fieldtype": "Int", "width": 80},
		{"fieldname": "tot_weekend", "label": "CT", "fieldtype": "Int", "width": 80},  # <-- tổng cuối tuần
		{"fieldname": "tot_absent",  "label": "V",  "fieldtype": "Int", "width": 80},
		# {"fieldname": "tot_late",  "label": "Late", "fieldtype": "Int", "width": 52},
		{"fieldname": "tot_miss",    "label": "QCC","fieldtype": "Int", "width": 80},
	]
	return base

# ====== helpers giữ nguyên y như trước, chỉ bổ sung _is_weekend ======
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

	# Active trong khoảng
	conds.append("(ifnull(relieving_date,'2099-12-31') >= %s)")
	vals.append(start_date)
	conds.append("(ifnull(date_of_joining,'1900-01-01') <= %s)")
	vals.append(end_date)

	if filters.get("department"):
		conds.append("department=%s")
		vals.append(filters["department"])
	if filters.get("employee"):
		conds.append("name=%s")
		vals.append(filters["employee"])

	sql = f"""
		SELECT name, employee_name, department, date_of_joining, relieving_date, holiday_list
		FROM `tabEmployee`
		WHERE {" AND ".join(conds)}
		ORDER BY department, employee_name
	"""
	return frappe.db.sql(sql, vals, as_dict=True)

def _holiday_map(emps, company, start_date, end_date):
	# map (emp, day) -> holiday description
	out = {}
	# default company holiday list
	comp_hl = frappe.db.get_value("Company", company, "default_holiday_list")
	# prefetch holidays for each list
	cache = {}
	def fetch_days(holiday_list):
		if not holiday_list:
			return set()
		if holiday_list in cache:
			return cache[holiday_list]
		rows = frappe.db.sql("""
			SELECT holiday_date, description
			FROM `tabHoliday`
			WHERE parent=%s AND holiday_date BETWEEN %s AND %s
		""", (holiday_list, start_date, end_date), as_dict=True)
		m = { (r.holiday_date, r.description or "Holiday") for r in rows }
		cache[holiday_list] = m
		return m

	for e in emps:
		hl = e.get("holiday_list") or comp_hl
		days = fetch_days(hl)
		for hd, desc in days:
			out[(e["name"], getdate(hd))] = desc
	return out

def _leave_map(emps, start_date, end_date):
	# map (emp, day) -> {leave_type, half_day, leave_name}
	out = {}
	emp_list = [e["name"] for e in emps]
	if not emp_list:
		return out
	rows = frappe.db.sql("""
		SELECT name, employee, from_date, to_date, half_day, half_day_date, leave_type
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
				"leave_name": r.name
			}
			cur += timedelta(days=1)
	return out

def _checkin_map(emps, start_date, end_date):
	# map (emp, day) -> agg
	out = {}
	emp_list = [e["name"] for e in emps]
	if not emp_list:
		return out
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
	"""Lấy shift start/end per employee per day từ Shift Assignment/Shift Type.
	   Nếu không có assignment ngày đó thì không map (để fallback sang giờ mặc định)."""
	out = {}
	emp_list = [e["name"] for e in emps]
	if not emp_list:
		return out
	# lấy assignment trong khoảng
	sd = min(days)
	ed = max(days)
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
		s_t = _parse_time(str(r.start_time))
		e_t = _parse_time(str(r.end_time))
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

def _hours_between(dt_in, dt_out):
	if not (dt_in and dt_out):
		return None
	secs = (dt_out - dt_in).total_seconds()
	return round(max(0, secs) / 3600.0, 2)

def _is_weekend(d: date) -> bool:
	"""Thứ 7/CN: weekday() 5,6."""
	return d.weekday() >= 5


def get_message() -> str:
	message = ""
	colors = [
		"green",
		"red",
		"orange",
		"#914EE3",
		"green",
		"#3187D8",
		"#878787",
		"#878787",
	]

	count = 0
	for status, abbr in STATUS_CODE.items():
		message += f"""
			<span style='border-left: 2px solid {colors[count]}; padding-right: 12px; padding-left: 5px; margin-right: 3px;'>
				{_(status)} - {abbr}
			</span>
		"""
		count += 1

	return message

def chart_data(rows):
	"""Tổng hợp dữ liệu để vẽ chart donut: X, P, L, CT, V, QCC"""
	agg = {"X": 0, "P": 0, "L": 0, "CT": 0, "V": 0, "QCC": 0}
	for r in rows:
		agg["X"]   += r.get("tot_present", 0)
		agg["P"]   += r.get("tot_leave", 0)
		agg["L"]   += r.get("tot_holiday", 0)
		agg["CT"]  += r.get("tot_weekend", 0)  # nếu chưa có tot_weekend, hàm vẫn an toàn (get default 0)
		agg["V"]   += r.get("tot_absent", 0)
		agg["QCC"] += r.get("tot_miss", 0)

	return {
		"data": {
			"labels": [
				"Đi làm (X)",
				"Nghỉ phép (P)",
				"Nghỉ lễ (L)",
				"Cuối tuần (CT)",
				"Vắng (V)",
				"Quên CC (QCC)",
			],
			"datasets": [
				{
					"name": "Số ngày",
					"values": [agg["X"], agg["P"], agg["L"], agg["CT"], agg["V"], agg["QCC"]],
				}
			],
		},
		"type": "donut",
	}
