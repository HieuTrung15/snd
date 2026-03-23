import frappe
from frappe import _
from frappe.utils import add_days, get_datetime, get_first_day, get_last_day, getdate, nowdate, today
from vinatex.vnt_hr.report.tổng_lương_cả_năm.tổng_lương_cả_năm import (
	get_company_salary_kpi,
	get_company_salary_chart,
)
from vinatex.vnt_hr.report.số_lượng_nhân_sự_theo_trình_độ_học_vấn.số_lượng_nhân_sự_theo_trình_độ_học_vấn import (
	get_data as get_education_distribution,
)
from vinatex.vnt_hr.report.số_nhân_sự_đi_làm_hôm_nay.số_nhân_sự_đi_làm_hôm_nay import (
	get_data as get_attendance_today_rows,
)

try:
	# frappe.desk.query_report.run exists on v13+
	from frappe.desk.query_report import run as run_report
except Exception:  # pragma: no cover - defensive for older stacks
	run_report = None


APPROVED_TRIP_STATES = {"Đã duyệt", "Duyệt"}
LEADER_WEEKLY_TRIP_DOCTYPE = "VNT Leader Weekly Trip"
LEADER_WEEKLY_TRIP_ITEM_DOCTYPE = "VNT Leader Weekly Trip Item"
PRIORITY_NAME_ORDER = {
	"Lê Tiến Trường": 0,
	"Cao Hữu Hiếu": 1,
	"Phạm Văn Tân": 2,
	"Nguyễn Đức Trị": 3,
	"Nguyễn Song Hải": 4,
	"Lê Mạc Thuấn": 5,
	"Nguyễn Thị Thu Hiền": 6,
}
DESIGNATION_PRIORITY = {"trưởng ban": 0, "chánh văn phòng": 1}


def _percent(part: float, total: float) -> float:
	return round((part / total) * 100, 1) if total else 0


def _safe_int(value) -> int:
	try:
		return int(value)
	except Exception:
		return 0


@frappe.whitelist()
def get_dashboard_data(company: str | None = None, department: str | None = None):
	"""
	Return a lightweight snapshot for the leadership HR dashboard.
	Data is kept intentionally small to keep the page responsive.
	"""
	filters = {k: v for k, v in {"company": company, "department": department}.items() if v}

	return {
		"cards": build_cards(filters),
		"charts": {
			"salary": build_salary_chart(filters),
			"education": build_education_chart(filters),
			"headcount": build_headcount_chart(filters),
			"turnover": build_turnover_chart(filters),
		},
		"tables": {
			"activity_summary": build_activity_summary(filters),
			"staff_movements": build_staff_movements(filters),
			"hr_reports": build_hr_reports_from_reminders(),
			"salary_cards": build_salary_cards(filters),
			"early_late": build_early_late_lists(filters),
			"present_managers": build_present_managers(filters),
		},
		"meta": {"filters": filters},
	}


def build_cards(filters: dict[str, str]) -> list[dict]:
	company = filters.get("company")
	department = filters.get("department")

	employee_filters = {"status": "Active"}
	if company:
		employee_filters["company"] = company
	if department:
		employee_filters["department"] = department

	total_active = frappe.db.count("Employee", employee_filters)

	today = getdate(nowdate())
	month_start = get_first_day(today)
	month_end = get_last_day(today)

	new_hires = count_employees_between("date_of_joining", month_start, month_end, company, department)
	attritions = count_employees_between("relieving_date", month_start, month_end, company, department)
	present_today = get_present_today(today, company, department)

	attendance_rate = _percent(present_today, total_active)
	attrition_rate = _percent(attritions, total_active)
	hiring_rate = _percent(new_hires, total_active)

	cards = [
		{
			"id": "total_employees",
			"title": _("Tổng số nhân sự"),
			"value": total_active,
			"display": f"{total_active:,}",
			"caption": _("Đang làm việc"),
			"progress": 100,
		},
		{
			"id": "attendance_today",
			"title": _("Số nhân sự đi làm hôm nay"),
			"value": attendance_rate,
			"display": f"{attendance_rate:.0f}%",
			"caption": _("{present}/{total}").format(present=present_today, total=total_active),
			"progress": attendance_rate,
		},
		{
			"id": "new_hires",
			"title": _("Nhân sự mới tháng này"),
			"value": new_hires,
			"display": str(new_hires),
			"caption": _("Nhân sự"),
			"progress": hiring_rate,
		},
		{
			"id": "attrition",
			"title": _("Nhân sự nghỉ việc tháng này"),
			"value": attritions,
			"display": str(attritions),
			"caption": _("Nhân sự"),
			"progress": attrition_rate,
		},
	]

	return cards


def build_salary_cards(filters: dict[str, str]) -> list[dict]:
	company = filters.get("company")
	cards: list[dict] = []
	try:
		salary_kpi = get_company_salary_kpi(company=company)
		if not salary_kpi:
			return cards
		cards.extend(
			[
				{
					"id": "salary_current_month",
					"title": _("Lương dự kiến tháng này"),
					"value": salary_kpi.get("total_year_salary", 0),
					"display": f"{salary_kpi.get('total_year_salary', 0):,.0f} đ",
					"caption": _("Trong tháng tính đến hiện tại"),
					"progress": 100,
				},
				{
					"id": "salary_prev_month",
					"title": _("Tổng lương tháng trước"),
					"value": salary_kpi.get("total_prev_month_salary", 0),
					"display": f"{salary_kpi.get('total_prev_month_salary', 0):,.0f} đ",
					"caption": _("Tổng đã chi tháng trươc"),
					"progress": 100,
				},
				{
					"id": "salary_paid_ytd",
					"title": _("Lương đã chi trong năm"),
					"value": salary_kpi.get("total_paid_salary_from_year_start", 0),
					"display": f"{salary_kpi.get('total_paid_salary_from_year_start', 0):,.0f} đ",
					"caption": _("Từ đầu năm"),
					"progress": 100,
				},
				{
					"id": "salary_fund_remaining",
					"title": _("Quỹ lương dự kiến còn lại"),
					"value": salary_kpi.get("total_to_date_salary", 0),
					"display": f"{salary_kpi.get('total_to_date_salary', 0):,.0f} đ",
					"caption": _("Quỹ lương năm - đã chi - dự kiến"),
					"progress": 100,
				},
				
			]
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - salary KPI")
	return cards


def build_salary_chart(filters: dict[str, str]) -> dict:
	company = filters.get("company")
	try:
		data = get_company_salary_chart(company=company)
		if data:
			return {
				"type": "line",
				"labels": data.get("categories") or [],
				"datasets": [
					{"name": _("Phụ cấp"), "values": data.get("allowance") or []},
					{"name": _("Tổng lương"), "values": data.get("salary") or []},
				],
				"colors": ["#22c55e", "#2563eb"],
			}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - salary chart")

	return {"type": "line", "labels": [], "datasets": [], "colors": ["#2563eb", "#22c55e"]}


def build_education_chart(filters: dict[str, str]) -> dict:
	company = filters.get("company")
	department = filters.get("department")

	try:
		data = get_education_distribution({"company": company, "department": department})
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - education chart")
		data = []

	if not data:
		return {"type": "bar", "labels": [], "datasets": [], "colors": ["#2563eb"]}

	labels = [row.get("qualification") for row in data]
	values = [row.get("employee_count") for row in data]

	return {
		"type": "bar",
		"labels": labels,
		"datasets": [{"name": _("Nhân sự"), "values": values}],
		"colors": ["#2563eb"],
	}


def build_early_late_lists(filters: dict[str, str]) -> dict:
	"""
	Lấy top đi sớm hôm nay và về muộn ngày hôm qua
	từ report `Số nhân sự đi làm hôm nay`.
	"""
	company = filters.get("company")
	department = filters.get("department")
	today_date = getdate(nowdate())
	yesterday = getdate(add_days(today_date, -1))
	rows_today: list[dict] = []
	rows_yday: list[dict] = []
	try:
		rows_today = get_attendance_today_rows(today_date, department=department)
		rows_yday = get_attendance_today_rows(yesterday, department=department)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - early/late")
		rows_today = []
		rows_yday = []

	if company:
		rows_today = _filter_rows_by_company(rows_today, company)
		rows_yday = _filter_rows_by_company(rows_yday, company)

	def _fmt(dt_val):
		if not dt_val:
			return ""
		try:
			return get_datetime(dt_val).strftime("%H:%M")
		except Exception:
			return str(dt_val)

	early = [
		{
			"employee": r.get("employee"),
			"employee_name": r.get("employee_name") or r.get("employee"),
			"department": r.get("department"),
			"branch": r.get("branch"),
			"time": _fmt(r.get("first_in")),
			"label": _("Đi sớm"),
		}
		for r in rows_today
		if r.get("first_in")
	]
	late = [
		{
			"employee": r.get("employee"),
			"employee_name": r.get("employee_name") or r.get("employee"),
			"department": r.get("department"),
			"branch": r.get("branch"),
			"time": _fmt(r.get("last_out")),
			"label": _("Về muộn"),
		}
		for r in rows_yday
		if r.get("last_out")
	]

	early.sort(key=lambda r: r["time"])
	late.sort(key=lambda r: r["time"], reverse=True)

	return {
		"early_arrivals": early[:5],
		"late_leavers": late[:5],
	}


def _filter_rows_by_company(rows: list[dict], company: str) -> list[dict]:
	employees = [r.get("employee") for r in rows if r.get("employee")]
	company_map = {}
	if employees:
		company_rows = frappe.get_all(
			"Employee",
			filters={"name": ("in", employees)},
			fields=["name", "company"],
			ignore_permissions=True,
		)
		company_map = {r.name: r.company for r in company_rows}
	return [r for r in rows if company_map.get(r.get("employee")) == company]


def build_headcount_chart(filters: dict[str, str]) -> dict:
	rows = []
	today = getdate(nowdate())
	report_filters = {
		"from_year": today.year,
		"from_month": 1,
		"to_year": today.year,
		"to_month": today.month,
		**filters,
	}

	if run_report:
		try:
			result = run_report("Số nhân sự hàng tháng", report_filters)
			rows = result.get("result") or result.get("message") or []
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - headcount report")

	labels = [row.get("month") or row.get("Tháng") for row in rows]
	headcounts = [_safe_int(row.get("headcount") or row.get("Số nhân sự (Headcount)")) for row in rows]
	averages = [_safe_int(row.get("avg_headcount") or row.get("Lao động bình quân năm")) for row in rows]

	return {
		"type": "column",
		"labels": labels,
		"datasets": [
			{"name": _("Số nhân sự"), "values": headcounts},
			{"name": _("Trung bình năm"), "values": averages},
		],
		"colors": ["#2563eb", "#94a3b8"],
	}


def build_turnover_chart(filters: dict[str, str]) -> dict:
	rows = []
	report_filters = {**filters}

	if run_report:
		try:
			result = run_report("NS tuyển mới với nghỉ việc", report_filters)
			rows = result.get("result") or result.get("message") or []
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - turnover report")

	labels = [row.get("month") or row.get("Tháng") for row in rows]
	hirings = [_safe_int(row.get("hiring_count") or row.get("Tuyển dụng")) for row in rows]
	attritions = [_safe_int(row.get("attrition_count") or row.get("Nghỉ việc")) for row in rows]

	return {
		"type": "line",
		"labels": labels,
		"datasets": [
			{"name": _("Tuyển mới"), "values": hirings},
			{"name": _("Nghỉ việc"), "values": attritions},
		],
		"colors": ["#0ea5e9", "#ef4444"],
		"lineOptions": {"regionFill": 1, "hideDots": 0, "dotSize": 3},
	}


def build_activity_summary(filters: dict[str, str]) -> list[dict]:
	"""Tóm tắt số người công tác / nghỉ hôm nay."""
	counts = count_attendance_movements(filters)
	return [
		{"kpi": _("Đang công tác"), "value": counts.get("trip", 0)},
		{"kpi": _("Đang nghỉ"), "value": counts.get("leave", 0)},
	]


def build_staff_movements(filters: dict[str, str]) -> list[dict]:
	"""Danh sách nhân sự công tác / nghỉ hôm nay, gồm Attendance và lịch tuần lãnh đạo."""
	ordering = {"Người quản lý": 1, "Lãnh đạo cấp trung": 2, "Chuyên viên, Nhân viên": 3}
	movements = get_attendance_movements(filters)
	rows: list[dict] = []
	today_date = getdate(today())
	for mv in movements:
		group = mv.get("group") or ""
		rows.append(
			{
				"employee": mv.get("employee"),
				"employee_name": mv.get("employee_name"),
				"designation": mv.get("designation"),
				"group": group,
				"status": mv.get("status"),
				"note": mv.get("note") or mv.get("leave_type") or "",
				"destination": mv.get("destination") or "",
				"_order": ordering.get(group, 99),
			}
		)
	trip_destination_map = _get_trip_destination_map(
		{
			row["employee"]
			for row in rows
			if row.get("status") == _("Công tác") and row.get("employee") and not row.get("destination")
		},
		today_date,
	)
	for row in rows:
		if row.get("status") == _("Công tác") and not row.get("destination"):
			row["destination"] = trip_destination_map.get(row.get("employee")) or ""
	rows.sort(
		key=lambda r: (
			* _leader_sort_key(r, group_code="department"),
			r.get("_order", 99),
			r.get("employee_name") or "",
		)
	)
	return rows


def get_attendance_movements(filters: dict[str, str]) -> list[dict]:
	"""Lấy nhân sự công tác / nghỉ hôm nay từ Attendance và lịch tuần lãnh đạo."""
	company = filters.get("company")
	department = filters.get("department")
	today_date = getdate(today())
	allowed_groups = {"Lãnh đạo cấp trung", "Người quản lý"}

	employees = frappe.get_all(
		"Employee",
		filters={
			"status": "Active",
			**({"company": company} if company else {}),
			**({"department": department} if department else {}),
		},
		fields=["name", "employee_name", "designation", "custom_designation_group"],
		ignore_permissions=True,
	)
	emp_map = {e.name: e for e in employees if (e.custom_designation_group in allowed_groups)}

	attendances = frappe.get_all(
		"Attendance",
		filters={
			"docstatus": 1,
			"status": "On Leave",
			"attendance_date": today_date,
			**({"company": company} if company else {}),
			**({"department": department} if department else {}),
		},
		fields=["employee", "employee_name", "leave_type", "company", "department"],
		ignore_permissions=True,
	)

	movement_by_employee: dict[str, dict] = {}
	for att in attendances:
		emp = emp_map.get(att.employee) or {}
		if not emp:
			continue
		leave_type = (att.leave_type or "").strip()
		leave_lower = leave_type.lower()
		status = _("Nghỉ")
		if "công tác" in leave_lower or "business" in leave_lower:
			status = _("Công tác")
		movement_by_employee[att.employee] = {
			"employee": att.employee,
			"employee_name": att.employee_name or emp.get("employee_name"),
			"designation": emp.get("designation"),
			"group": emp.get("custom_designation_group") or "",
			"status": status,
			"leave_type": leave_type,
			"note": leave_type,
			"destination": "",
		}

	weekly_trip_destinations = _get_leader_weekly_trip_destination_map(today_date, set(emp_map.keys()))
	for employee, destination in weekly_trip_destinations.items():
		emp = emp_map.get(employee) or {}
		if not emp:
			continue
		existing = movement_by_employee.get(employee) or {}
		movement_by_employee[employee] = {
			"employee": employee,
			"employee_name": existing.get("employee_name") or emp.get("employee_name"),
			"designation": existing.get("designation") or emp.get("designation"),
			"group": existing.get("group") or emp.get("custom_designation_group") or "",
			"status": _("Công tác"),
			"leave_type": existing.get("leave_type") or "",
			"note": existing.get("note") or _("Công tác"),
			"destination": destination,
		}
	# Nếu không có dữ liệu, thêm mẫu cho dashboard (tránh rỗng UI)
	# if not rows:
	#     rows = [
	#         {
	#             "employee": "EMP-CT",
	#             "employee_name": _("Nguyễn Văn Công"),
	#             "designation": _("Chuyên viên"),
	#             "group": _("Chuyên viên, Nhân viên"),
	#             "status": _("Công tác"),
	#             "leave_type": _("Công tác"),
	#             "note": _("Công tác"),
	#             "_order": ordering.get(_("Chuyên viên, Nhân viên"), 3),
	#         },
	#         {
	#             "employee": "EMP-NN",
	#             "employee_name": _("Trần Thị Nghỉ"),
	#             "designation": _("Nhân viên"),
	#             "group": _("Chuyên viên, Nhân viên"),
	#             "status": _("Nghỉ"),
	#             "leave_type": _("Nghỉ phép năm"),
	#             "note": _("Nghỉ phép năm"),
	#             "_order": ordering.get(_("Chuyên viên, Nhân viên"), 3),
	#         },
	#     ]

	return list(movement_by_employee.values())


def count_attendance_movements(filters: dict[str, str]) -> dict[str, int]:
	movements = get_attendance_movements(filters)
	counts = {"trip": 0, "leave": 0}
	for mv in movements:
		if mv.get("status") == _("Công tác"):
			counts["trip"] += 1
		else:
			counts["leave"] += 1
	return counts


def _filter_by_days(items: list[dict], field: str, max_days: int) -> list[dict]:
	today_date = getdate(nowdate())
	filtered: list[dict] = []
	for row in items or []:
		dt_val = row.get(field)
		if not dt_val:
			continue
		try:
			delta = (getdate(dt_val) - today_date).days
		except Exception:
			continue
		if 0 <= delta <= max_days:
			filtered.append(row)
	return filtered


def build_hr_reports_from_reminders() -> dict:
	"""
	Chia 3 nhóm: Hợp đồng hết hạn (30 ngày tới), Sinh nhật (30 ngày tới), Nghỉ hưu (60 ngày tới)
	và trả về tổng số + danh sách gọn cho UI mới.
	"""
	reminders = safe_get_hr_reminders(days_ahead=90, limit=50)
	stats = _get_avg_age_tenure()

	contracts = _filter_by_days(reminders.get("contracts_expiring", []), "end_date", 30)
	birthdays = _filter_by_days(reminders.get("birthdays", []), "next_birthday", 30)
	retirements = _filter_by_days(reminders.get("retirements", []), "date_of_retirement", 60)
	emp_status_map = _get_employee_status_map(
		{row.get("employee") for row in contracts + retirements if row.get("employee")}
	)

	def _map(rows, date_field: str, status_func) -> list[dict]:
		result: list[dict] = []
		for row in rows:
			emp = row.get("employee")
			emp_status = emp_status_map.get(emp)
			date_val = row.get(date_field)
			date_fmt = ""
			if date_val:
				try:
					date_fmt = getdate(date_val).strftime("%d/%m/%Y")
				except Exception:
					date_fmt = str(date_val)
			result.append(
				{
					"label": row.get("employee_name") or row.get("employee"),
					"date": date_fmt,
					"status": status_func(row, emp_status),
				}
			)
		return result

	today_date = getdate(nowdate())

	def contract_status(row, emp_status: str | None):
		end_date = row.get("end_date")
		if end_date:
			try:
				if getdate(end_date) < today_date and (emp_status or "").lower() == "active":
					return _("Đã hết hạn")
			except Exception:
				pass
		return _("Sắp hết hạn")

	def retirement_status(row, emp_status: str | None):
		retire_date = row.get("date_of_retirement")
		if retire_date:
			try:
				if getdate(retire_date) < today_date and (emp_status or "").lower() == "active":
					return _("Đã nghỉ hưu")
			except Exception:
				pass
		return _("Sắp tới")

	def birthday_status(row, emp_status: str | None):
		return ""

	return {
		"contracts": {"count": len(contracts), "items": _map(contracts, "end_date", contract_status)},
		"birthdays": {"count": len(birthdays), "items": _map(birthdays, "next_birthday", birthday_status)},
		"retirements": {
			"count": len(retirements),
			"items": _map(retirements, "date_of_retirement", retirement_status),
		},
		"stats": stats,
	}


def _get_employee_status_map(emp_names: set[str]) -> dict[str, str]:
	if not emp_names:
		return {}
	rows = frappe.get_all(
		"Employee",
		filters={"name": ("in", list(emp_names))},
		fields=["name", "status"],
		ignore_permissions=True,
	)
	return {r.name: r.status for r in rows}


def _get_avg_age_tenure() -> dict:
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "date_of_birth", "date_of_joining"],
	)
	today_date = getdate(nowdate())
	ages = []
	tenures = []

	def _years_between(dt_val):
		return max((today_date - getdate(dt_val)).days / 365.25, 0)

	for emp in employees:
		if emp.date_of_birth:
			try:
				ages.append(_years_between(emp.date_of_birth))
			except Exception:
				pass
		if emp.date_of_joining:
			try:
				tenures.append(_years_between(emp.date_of_joining))
			except Exception:
				pass

	def _avg(lst: list[float]) -> float:
		return round(sum(lst) / len(lst), 1) if lst else 0

	return {"avg_age": _avg(ages), "avg_tenure": _avg(tenures)}


def count_employees_between(fieldname: str, start_date, end_date, company: str | None, department: str | None) -> int:
	if not start_date or not end_date:
		return 0

	conditions = [f"{fieldname} BETWEEN %(start)s AND %(end)s"]
	params = {"start": start_date, "end": end_date}

	if company:
		conditions.append("company = %(company)s")
		params["company"] = company
	if department:
		conditions.append("department = %(department)s")
		params["department"] = department

	query = f"SELECT COUNT(*) FROM `tabEmployee` WHERE {' AND '.join(conditions)}"
	return _safe_int(frappe.db.sql(query, params)[0][0])


def get_present_today(the_date, company: str | None, department: str | None) -> int:
	"""
	Đếm nhân sự đi làm hôm nay theo cùng logic với report
	`Số nhân sự đi làm hôm nay` (dựa trên Employee Checkin).
	"""
	try:
		rows = get_attendance_today_rows(
			the_date,
			department=department,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - present today")
		rows = []

	if company:
		employees = [r.get("employee") for r in rows if r.get("employee")]
		company_map = {}
		if employees:
			company_rows = frappe.get_all("Employee", filters={"name": ("in", employees)}, fields=["name", "company"])
			company_map = {r.name: r.company for r in company_rows}
		rows = [r for r in rows if company_map.get(r.get("employee")) == company]

	return len(rows)


def safe_get_hr_reminders(days_ahead: int = 60, limit: int = 5) -> dict:
	try:
		return frappe.get_attr("vinatex.api.hr_reminders.get_hr_reminders")(days_ahead=days_ahead, limit=limit)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - hr_reminders")
		return {}


def build_present_managers(filters: dict[str, str]) -> dict[str, list[dict]]:
	"""Nhân sự có mặt tại công ty (leader/mid) hôm nay dựa trên report attendance today, tách 2 nhóm."""
	allowed_groups = {"Lãnh đạo cấp trung", "Người quản lý"}
	excluded_designation = "thành viên ban kiểm soát không chuyên trách tập đoàn"
	dept_member_designation_raw = "Thành viên Ban Kiểm soát chuyên trách Tập đoàn"
	dept_member_designation = dept_member_designation_raw.lower()
	company = filters.get("company")
	department = filters.get("department")
	today_date = getdate(nowdate())

	try:
		rows = get_attendance_today_rows(today_date, department=department)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - present managers")
		rows = []

	leader_rows = frappe.get_all(
		"Employee",
		filters={
			"status": "Active",
			**({"company": company} if company else {}),
			**({"department": department} if department else {}),
		},
		or_filters=[
			{"custom_designation_group": ("in", list(allowed_groups))},
			{"designation": ("like", "%Ban Kiểm soát chuyên trách Tập đoàn%")},
		],
		fields=[
			"name",
			"employee_name",
			"department",
			"designation",
			"custom_designation_group",
			"company",
			"custom_need_check",
		],
		ignore_permissions=True,
	)
	leader_map = {e.name: e for e in leader_rows}
	leader_ids = set(leader_map.keys())

	# Những người đang công tác/nghỉ hôm nay (để không auto-mark có mặt)
	on_leave_or_trip = _get_absent_employee_ids(today_date, leader_ids)

	def _classify(emp) -> str | None:
		designation = (emp.get("designation") or "").strip().lower()
		if designation == excluded_designation:
			return None
		if designation == dept_member_designation:
			return "department"
		group = emp.get("custom_designation_group")
		dept = emp.get("department")
		if group == "Người quản lý" and dept != "Ban Kiểm soát":
			return "corporate"
		if (group == "Người quản lý" and dept == "Ban Kiểm soát") or group == "Lãnh đạo cấp trung":
			return "department"
		return None

	def _fmt(dt_val):
		if not dt_val:
			return ""
		try:
			return get_datetime(dt_val).strftime("%H:%M")
		except Exception:
			return str(dt_val)

	result = {"corporate": [], "department": []}
	checkin_present_ids: set[str] = set()
	for r in rows:
		emp_code = r.get("employee")
		if not emp_code or emp_code in on_leave_or_trip:
			continue
		emp = leader_map.get(emp_code)
		if not emp:
			continue
		group_code = _classify(emp)
		if not group_code:
			continue
		if company and emp.get("company") != company:
			continue
		# Lãnh đạo ban không lấy theo checkin, chỉ auto-mark phía dưới
		if group_code == "department":
			continue
		checkin_present_ids.add(emp_code)
		result[group_code].append(
			{
				"employee": emp_code,
				"employee_name": emp.get("employee_name") or emp_code,
				"department": emp.get("department"),
				"designation": emp.get("designation"),
				"time": _fmt(r.get("first_in")),
				"group": group_code,
			}
		)

	# Auto-mark present nếu có custom_need_check = 1 và không công tác/nghỉ
	for emp in leader_rows:
		if emp.name in checkin_present_ids:
			continue
		if emp.name in on_leave_or_trip:
			continue
		group_code = _classify(emp)
		if not group_code:
			continue
		result[group_code].append(
			{
				"employee": emp.name,
				"employee_name": emp.get("employee_name") or emp.name,
				"department": emp.get("department"),
				"designation": emp.get("designation"),
				"time": "",
				"group": group_code,
			}
		)

	for grp_name, grp in result.items():
		grp.sort(key=lambda row: _leader_sort_key(row, grp_name))

	return {
		"corporate_leaders": result["corporate"],
		"department_leaders": result["department"],
	}


def _get_trip_destination_map(employees: set[str], the_date) -> dict[str, str]:
	"""Lấy địa điểm công tác (destination) cho danh sách nhân viên trong ngày."""
	if not employees:
		return {}
	try:
		requests = frappe.get_all(
			"VNT Business Trip Request",
			filters={
				"workflow_state": ("in", list(APPROVED_TRIP_STATES)),
				"from_date": ("<=", the_date),
				"to_date": (">=", the_date),
			},
			fields=["name", "employee", "destination"],
			ignore_permissions=True,
		)
		parent_map = {r.name: r for r in requests}
		dest_map: dict[str, str] = {}

		for r in requests:
			if r.get("employee") in employees:
				dest_map[r.get("employee")] = r.get("destination") or ""

		if parent_map:
			item_rows = frappe.get_all(
				"VNT Business Trip Request Items",
				filters={"parent": ("in", list(parent_map.keys())), "employee": ("in", list(employees))},
				fields=["employee", "parent"],
				ignore_permissions=True,
			)
			for item in item_rows:
				parent = parent_map.get(item.parent)
				if not parent:
					continue
				if item.employee in employees:
					dest_map[item.employee] = parent.get("destination") or ""

		for employee, destination in _get_leader_weekly_trip_destination_map(the_date, employees).items():
			if destination:
				dest_map[employee] = destination

		return dest_map
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - trip destinations")
		return {}


def _get_leader_weekly_trip_rows_on_date(the_date, employees: set[str] | None = None) -> list[dict]:
	"""Danh sách dòng lịch tuần lãnh đạo đúng ngày cần hiển thị."""
	if not the_date:
		return []
	if employees is not None and not employees:
		return []
	try:
		parents = frappe.get_all(
			LEADER_WEEKLY_TRIP_DOCTYPE,
			filters={
				"docstatus": ("<", 2),
				"from_date": ("<=", the_date),
				"to_date": (">=", the_date),
			},
			fields=["name"],
			ignore_permissions=True,
		)
		parent_names = [row.name for row in parents if row.name]
		if not parent_names:
			return []

		item_filters = {
			"parent": ("in", parent_names),
			"trip_date": the_date,
		}
		if employees:
			item_filters["employee"] = ("in", list(employees))

		return frappe.get_all(
			LEADER_WEEKLY_TRIP_ITEM_DOCTYPE,
			filters=item_filters,
			fields=["parent", "employee", "employee_name", "destination", "purpose", "time_slot"],
			ignore_permissions=True,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - leader weekly trip rows")
		return []


def _format_leader_weekly_trip_destination(destination: str | None, time_slot: str | None) -> str:
	destination_text = (destination or "").strip() or "(chưa có địa điểm)"
	slot = (time_slot or "").strip() or "Cả ngày"
	if slot in {"Sáng", "Chiều"}:
		return f"[{slot}] {destination_text}"
	return destination_text


def _get_leader_weekly_trip_destination_map(the_date, employees: set[str] | None = None) -> dict[str, str]:
	"""Gom địa điểm công tác từ lịch tuần lãnh đạo theo từng nhân sự trong ngày."""
	trip_rows = _get_leader_weekly_trip_rows_on_date(the_date, employees)
	if not trip_rows:
		return {}

	destination_map: dict[str, list[str]] = {}
	for row in trip_rows:
		employee = row.get("employee")
		if not employee:
			continue
		destination_map.setdefault(employee, []).append(
			_format_leader_weekly_trip_destination(row.get("destination"), row.get("time_slot"))
		)

	return {employee: " | ".join(dict.fromkeys(destinations)) for employee, destinations in destination_map.items()}


def _get_trip_employees_on_date(the_date, employees: set[str] | None = None) -> set[str]:
	"""Danh sách mã NV có đơn công tác (được duyệt) trùng ngày."""
	if not the_date:
		return set()
	if employees is not None and not employees:
		return set()
	try:
		parent_filters = {
			"workflow_state": ("in", list(APPROVED_TRIP_STATES)),
			"docstatus": 1,
			"from_date": ("<=", the_date),
			"to_date": (">=", the_date),
		}
		if employees:
			parent_filters["employee"] = ("in", list(employees))

		requests = frappe.get_all(
			"VNT Business Trip Request",
			filters=parent_filters,
			fields=["name", "employee"],
			ignore_permissions=True,
		)
		req_names = [r.name for r in requests]
		trip_emp = {r.employee for r in requests if r.employee}

		if req_names:
			item_filters = {"parent": ("in", req_names)}
			if employees:
				item_filters["employee"] = ("in", list(employees))
			items = frappe.get_all(
				"VNT Business Trip Request Items",
				filters=item_filters,
				fields=["employee"],
				ignore_permissions=True,
			)
			for item in items:
				if item.employee:
					trip_emp.add(item.employee)

		trip_emp.update(
			row.get("employee")
			for row in _get_leader_weekly_trip_rows_on_date(the_date, employees)
			if row.get("employee")
		)

		if employees:
			trip_emp = {emp for emp in trip_emp if emp in employees}
		return trip_emp
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - trip employees on date")
		return set()


def _get_absent_employee_ids(the_date, employees: set[str] | None = None) -> set[str]:
	"""Hợp nhất danh sách nghỉ phép/công tác trong ngày để lọc khỏi danh sách có mặt."""
	if not the_date:
		return set()
	if employees is not None and not employees:
		return set()

	emp_filter = {"employee": ("in", list(employees))} if employees else {}
	absent: set[str] = set()

	# Nghỉ phép
	try:
		leave_rows = frappe.get_all(
			"Leave Application",
			filters={
				"docstatus": 1,
				"from_date": ("<=", the_date),
				"to_date": (">=", the_date),
				**emp_filter,
			},
			fields=["employee"],
			ignore_permissions=True,
		)
		absent.update(r.employee for r in leave_rows if r.employee)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - leave on date")

	# Attendance On Leave (phòng trường hợp không có đơn)
	try:
		att_rows = frappe.get_all(
			"Attendance",
			filters={"docstatus": 1, "status": "On Leave", "attendance_date": the_date, **emp_filter},
			fields=["employee"],
			ignore_permissions=True,
		)
		absent.update(r.employee for r in att_rows if r.employee)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership Dashboard - attendance on leave")

	# Công tác
	absent.update(_get_trip_employees_on_date(the_date, employees))

	return absent


def _leader_sort_key(row: dict, group_code: str | None = None) -> tuple:
	"""
	Sắp xếp ưu tiên theo tên nổi bật trước, sau đó chức danh; dùng cho cả danh sách lãnh đạo & công tác/nghỉ.
	group_code "department" sẽ áp dụng ưu tiên chức danh.
	"""
	name = (row.get("employee_name") or "").strip()
	designation = (row.get("designation") or "").strip().lower()
	time_val = row.get("time") or ""
	name_order = PRIORITY_NAME_ORDER.get(name, 99)
	designation_order = DESIGNATION_PRIORITY.get(designation, 99) if group_code == "department" else 99
	return (name_order, designation_order, time_val, name)
