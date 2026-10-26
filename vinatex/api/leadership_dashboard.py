"""Source-backed morning snapshot for the Leadership workspace."""

from __future__ import annotations

import json
from collections import Counter
from datetime import timedelta
from math import ceil

import frappe
from frappe import _
from frappe.utils import add_months, cint, get_datetime, get_first_day, getdate, now_datetime, today
from frappe.utils.caching import redis_cache

from vinatex.api.hr_dashboard import (
	_normalize_branches,
	_resolve_as_of_date,
	get_employee_branches,
	get_hr_dashboard_snapshot,
)
from vinatex.api.hr_reminders import get_hr_reminders
from vinatex.vnt_hr.doctype.vnt_salary_slip.vnt_salary_slip import VNTSalarySlip, _needs_decryption
from vinatex.vnt_hr.attendance_processing import (
	build_shift_windows,
	calculate_attendance_details,
	classify_work_date,
	load_checkins_for_windows,
	load_holiday_context,
)
from vinatex.vnt_hr.report.ns_tuyển_mới_với_nghỉ_việc.ns_tuyển_mới_với_nghỉ_việc import (
	execute as get_turnover_report,
)
from vinatex.vnt_hr.report.số_nhân_sự_đi_làm_hôm_nay.số_nhân_sự_đi_làm_hôm_nay import (
	get_data as get_attendance_rows,
)


LEADERSHIP_GROUPS = {"Người quản lý", "Lãnh đạo cấp trung"}
APPROVED_TRIP_STATES = {"Đã duyệt", "Duyệt"}
LEADERSHIP_ROLES = {"HR Manager", "System Manager"}
LEADERSHIP_DESIGNATION_MARKERS = (
	"giám đốc",
	"quản đốc",
	"trưởng phòng",
	"phó phòng",
	"trưởng ca",
	"phó trưởng ca",
	"trưởng công đoạn",
	"phó công đoạn",
)


def _number(value) -> float:
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def _month_number(value) -> int:
	try:
		month = int(str(value or "").strip())
		return month if 1 <= month <= 12 else 0
	except (TypeError, ValueError):
		return 0


def _resolve_scope(as_of_date=None, branches=None, branch=None, company=None):
	if not frappe.has_permission("Employee", "read"):
		frappe.throw(_("Bạn không có quyền xem dữ liệu nhân sự."), frappe.PermissionError)
	if not LEADERSHIP_ROLES.intersection(frappe.get_roles()):
		frappe.throw(_("Bạn không có quyền xem Bảng tin lãnh đạo."), frappe.PermissionError)

	date_value = _resolve_as_of_date(as_of_date)
	company_value = (
		company
		or frappe.defaults.get_user_default("Company")
		or frappe.defaults.get_global_default("company")
		or ""
	).strip()
	if not company_value:
		frappe.throw(_("Vui lòng thiết lập công ty mặc định trước khi xem Bảng tin lãnh đạo."))
	branch_values = _normalize_branches(branches or branch)
	allowed_branches = tuple(get_employee_branches(company=company_value))
	invalid = sorted(set(branch_values) - set(allowed_branches))
	if invalid:
		frappe.throw(_("Chi nhánh không thuộc phạm vi dữ liệu được phép xem: {0}").format(", ".join(invalid)))

	return date_value, company_value, branch_values, allowed_branches


def _employee_scope_conditions(as_of_date, company: str, branches: tuple[str, ...]):
	params = {"as_of_date": as_of_date, "company": company, "branches": branches}
	conditions = ["e.status = 'Active'"]
	if as_of_date != getdate(today()):
		conditions.extend([
			"e.date_of_joining <= %(as_of_date)s",
			"(e.relieving_date IS NULL OR e.relieving_date > %(as_of_date)s)",
		])
	if company:
		conditions.append("e.company = %(company)s")
	if branches:
		conditions.append("e.branch IN %(branches)s")
	return conditions, params


def _get_scoped_employees(as_of_date, company: str, branches: tuple[str, ...]) -> list[dict]:
	conditions, params = _employee_scope_conditions(as_of_date, company, branches)
	return frappe.db.sql(
		f"""
		SELECT e.name, e.employee_name, e.company, e.branch, e.department,
		       e.designation, e.custom_designation_group, e.date_of_birth,
		       e.date_of_joining, e.relieving_date, e.holiday_list,
		       e.default_shift, e.custom_shift_group, e.custom_need_check
		FROM `tabEmployee` e
		WHERE {' AND '.join(conditions)}
		ORDER BY e.employee_name
		""",
		params,
		as_dict=True,
	)


def _format_time(value) -> str:
	if not value:
		return ""
	try:
		return get_datetime(value).strftime("%H:%M")
	except Exception:
		text = str(value)
		return text[11:16] if len(text) >= 16 else text


def _leave_map(as_of_date, employee_ids: tuple[str, ...]) -> dict[str, dict]:
	if not employee_ids:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT live.employee, live.leave_type, live.half_day, live.source_order
		FROM (
			SELECT la.employee, la.leave_type, la.half_day, 1 AS source_order
			FROM `tabLeave Application` la
			WHERE la.docstatus = 1
			  AND la.from_date <= %(date)s AND la.to_date >= %(date)s
			  AND la.employee IN %(employees)s
			UNION ALL
			SELECT att.employee, att.leave_type, 0 AS half_day, 2 AS source_order
			FROM `tabAttendance` att
			WHERE att.docstatus = 1 AND att.status = 'On Leave'
			  AND att.attendance_date = %(date)s
			  AND att.employee IN %(employees)s
		) live
		ORDER BY live.source_order
		""",
		{"date": as_of_date, "employees": employee_ids},
		as_dict=True,
	)
	result = {}
	for row in rows:
		leave_type = (row.get("leave_type") or "").strip()
		if "công tác" in leave_type.casefold() or "business trip" in leave_type.casefold():
			continue
		if row.employee in result:
			continue
		detail = leave_type or _("Nghỉ")
		if cint(row.get("half_day")):
			detail = _("{0} · Nửa ngày").format(detail)
		result[row.employee] = {"detail": detail}
	return result


def _trip_map(as_of_date, employee_ids: tuple[str, ...]) -> dict[str, dict]:
	if not employee_ids:
		return {}
	result: dict[str, dict] = {}
	try:
		meta = frappe.get_meta("VNT Business Trip Request")
		filters = {
			"docstatus": 1,
			"from_date": ("<=", as_of_date),
			"to_date": (">=", as_of_date),
		}
		fields = ["name", "employee", "destination", "purpose"]
		if meta.has_field("workflow_state"):
			filters["workflow_state"] = ("in", list(APPROVED_TRIP_STATES))
		parents = frappe.get_all(
			"VNT Business Trip Request",
			filters=filters,
			fields=fields,
			ignore_permissions=True,
		)
		parent_map = {row.name: row for row in parents}
		for row in parents:
			if row.employee in employee_ids:
				result[row.employee] = {
					"detail": row.destination or row.purpose or _("Công tác"),
					"destination": row.destination or "",
				}

		if parent_map:
			items = frappe.get_all(
				"VNT Business Trip Request Items",
				filters={"parent": ("in", list(parent_map)), "employee": ("in", list(employee_ids))},
				fields=["parent", "employee"],
				ignore_permissions=True,
			)
			for item in items:
				parent = parent_map.get(item.parent)
				if parent:
					result[item.employee] = {
						"detail": parent.destination or parent.purpose or _("Công tác"),
						"destination": parent.destination or "",
					}

		if frappe.db.exists("DocType", "VNT Leader Weekly Trip"):
			parents = frappe.get_all(
				"VNT Leader Weekly Trip",
				filters={"docstatus": ("<", 2), "from_date": ("<=", as_of_date), "to_date": (">=", as_of_date)},
				pluck="name",
				ignore_permissions=True,
			)
			if parents:
				items = frappe.get_all(
					"VNT Leader Weekly Trip Item",
					filters={"parent": ("in", parents), "trip_date": as_of_date, "employee": ("in", list(employee_ids))},
					fields=["employee", "destination", "purpose", "time_slot"],
					ignore_permissions=True,
				)
				for item in items:
					detail = item.destination or item.purpose or _("Công tác")
					if item.time_slot in {"Sáng", "Chiều"}:
						detail = f"{item.time_slot}: {detail}"
					result[item.employee] = {"detail": detail, "destination": item.destination or ""}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership snapshot - business trips")
	return result


def _build_attendance(as_of_date, employees: list[dict]) -> dict:
	employee_map = {row.name: row for row in employees}
	employee_ids = tuple(employee_map)
	leave_map = _leave_map(as_of_date, employee_ids)
	trip_map = _trip_map(as_of_date, employee_ids)

	try:
		attendance_rows = get_attendance_rows(as_of_date) or []
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership snapshot - checkins")
		attendance_rows = []
	checkins = {row.get("employee"): row for row in attendance_rows if row.get("employee") in employee_map}

	trip_ids = set(trip_map)
	leave_ids = set(leave_map) - trip_ids
	present_ids = set(checkins) - leave_ids - trip_ids
	recorded_ids = present_ids | leave_ids | trip_ids
	unrecorded_ids = set(employee_map) - recorded_ids
	expected = max(len(employee_map) - len(leave_ids) - len(trip_ids), 0)
	present_rate = round(len(present_ids) / expected * 100, 1) if expected else 0
	coverage_rate = round(len(recorded_ids) / len(employee_map) * 100, 1) if employee_map else 0

	leaders = []
	for employee_id, employee in employee_map.items():
		designation_key = (employee.get("designation") or "").casefold()
		is_leader = employee.get("custom_designation_group") in LEADERSHIP_GROUPS or any(
			marker in designation_key for marker in LEADERSHIP_DESIGNATION_MARKERS
		)
		if not is_leader:
			continue
		status = "unrecorded"
		status_label = _("Chưa ghi nhận")
		detail = ""
		if employee_id in trip_ids:
			status, status_label = "trip", _("Công tác")
			detail = trip_map[employee_id].get("detail") or ""
		elif employee_id in leave_ids:
			status, status_label = "leave", _("Nghỉ")
			detail = leave_map[employee_id].get("detail") or ""
		elif employee_id in present_ids:
			status, status_label = "present", _("Có mặt")
			detail = _format_time(checkins[employee_id].get("first_in"))
		leaders.append(
			{
				"employee": employee_id,
				"employee_name": employee.employee_name or employee_id,
				"designation": employee.designation or "",
				"department": employee.department or "",
				"status": status,
				"status_label": status_label,
				"detail": detail,
			}
		)
	status_order = {"trip": 0, "leave": 1, "present": 2, "unrecorded": 3}
	leaders.sort(key=lambda row: (status_order.get(row["status"], 9), row["employee_name"]))

	return {
		"total": len(employee_map),
		"present": len(present_ids),
		"leave": len(leave_ids),
		"trip": len(trip_ids),
		"unrecorded": len(unrecorded_ids),
		"expected": expected,
		"present_rate": present_rate,
		"coverage_rate": coverage_rate,
		"leaders": leaders,
	}


def _format_date(value) -> str:
	if not value:
		return ""
	try:
		return getdate(value).strftime("%d/%m/%Y")
	except Exception:
		return str(value)


def _days_between(start, value) -> int | None:
	try:
		return (getdate(value) - start).days
	except Exception:
		return None


def _pending_leave_items(as_of_date, company: str, branches: tuple[str, ...]) -> list[dict]:
	conditions = ["la.docstatus = 0", "la.status = 'Open'"]
	params = {"company": company, "branches": branches}
	if company:
		conditions.append("e.company = %(company)s")
	if branches:
		conditions.append("e.branch IN %(branches)s")
	rows = frappe.db.sql(
		f"""
		SELECT la.name, la.employee, COALESCE(NULLIF(la.employee_name, ''), e.employee_name) AS employee_name,
		       la.leave_type, la.from_date, la.to_date, e.department
		FROM `tabLeave Application` la
		INNER JOIN `tabEmployee` e ON e.name = la.employee
		WHERE {' AND '.join(conditions)}
		ORDER BY la.from_date ASC, la.creation ASC
		""",
		params,
		as_dict=True,
	)
	return [
		{
			"label": row.employee_name or row.employee,
			"date": _format_date(row.from_date),
			"detail": row.leave_type or row.department or "",
			"name": row.name,
		}
		for row in rows
	]


def _build_attention(as_of_date, company: str, branches: tuple[str, ...]) -> list[dict]:
	try:
		reminders = get_hr_reminders(
			days_ahead=365,
			limit=500,
			include_retirements=1,
			branches=branches,
			as_of_date=str(as_of_date),
			company=company,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership snapshot - reminders")
		reminders = {}

	contracts = [
		row for row in reminders.get("contracts_expiring", [])
		if (_days_between(as_of_date, row.get("end_date")) or 0) <= 30
	]
	birthdays = [
		row for row in reminders.get("birthdays", [])
		if (_days_between(as_of_date, row.get("next_birthday")) or 0) <= 30
	]
	retirements = reminders.get("retirements", [])
	pending = _pending_leave_items(as_of_date, company, branches)

	def mapped(rows, date_field):
		return [
			{
				"label": row.get("employee_name") or row.get("employee") or "",
				"date": _format_date(row.get(date_field)),
				"detail": row.get("department") or "",
			}
			for row in rows[:5]
		]

	return [
		{
			"id": "contracts",
			"title": _("Hợp đồng sắp hết hạn"),
			"value": len(contracts),
			"caption": _("Trong 30 ngày tới"),
			"tone": "amber",
			"route": "/app/vnt-contract",
			"items": mapped(contracts, "end_date"),
		},
		{
			"id": "approvals",
			"title": _("Nghỉ phép chờ duyệt"),
			"value": len(pending),
			"caption": _("Cần xem xét hiện tại"),
			"tone": "pink",
			"route": "/app/leave-application",
			"items": pending[:5],
		},
		{
			"id": "retirements",
			"title": _("Nhân sự đến tuổi nghỉ hưu"),
			"value": len(retirements),
			"caption": _("Trong 12 tháng tới"),
			"tone": "violet",
			"route": "/app/query-report/Báo cáo cán bộ đến tuổi nghỉ hưu",
			"items": mapped(retirements, "date_of_retirement"),
		},
		{
			"id": "birthdays",
			"title": _("Sinh nhật sắp tới"),
			"value": len(birthdays),
			"caption": _("Trong 30 ngày tới"),
			"tone": "blue",
			"route": "/app/employee",
			"items": mapped(birthdays, "next_birthday"),
		},
	]


def _build_turnover(as_of_date, company: str, branches: tuple[str, ...]) -> dict:
	filters = {
		"from_date": add_months(get_first_day(as_of_date), -11),
		"to_date": as_of_date,
		"company": company,
		"branches": list(branches),
	}
	try:
		_report_columns, rows, *_report_tail = get_turnover_report(filters)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Leadership snapshot - turnover")
		rows = []
	labels = [str(row.get("month") or "").replace("-", "/") for row in rows]
	hiring = [cint(row.get("hiring_count")) for row in rows]
	attrition = [cint(row.get("attrition_count")) for row in rows]
	return {
		"labels": labels,
		"datasets": [
			{"name": _("Tuyển mới"), "values": hiring},
			{"name": _("Nghỉ việc"), "values": attrition},
		],
		"summary": {
			"hiring": sum(hiring),
			"attrition": sum(attrition),
			"net": sum(hiring) - sum(attrition),
		},
	}


def _salary_values(row) -> tuple[float, float]:
	gross = row.get("tong_thu_nhap")
	net = row.get("thuc_linh")
	if _needs_decryption(gross, row.get("tong_thu_nhap_encrypted")) or _needs_decryption(
		net, row.get("thuc_linh_encrypted")
	):
		decrypted = VNTSalarySlip.decrypt_salary_values(
			tong_thu_nhap_encrypted=row.get("tong_thu_nhap_encrypted"),
			thuc_linh_encrypted=row.get("thuc_linh_encrypted"),
		)
		gross = decrypted.get("tong_thu_nhap")
		net = decrypted.get("thuc_linh")
	return _number(gross), _number(net)


def _build_finance(as_of_date, company: str, branches: tuple[str, ...]) -> dict:
	if not frappe.has_permission("VNT Salary Slip", "read"):
		return {
			"available": False,
			"has_data": False,
			"message": _("Tài khoản chưa được cấp quyền xem dữ liệu bảng lương."),
		}

	previous_date = getdate(add_months(as_of_date, -1))
	conditions = ["slip.docstatus = 1", "CAST(slip.year AS UNSIGNED) IN %(years)s"]
	params = {
		"years": tuple(sorted({as_of_date.year, previous_date.year})),
		"company": company,
		"branches": branches,
	}
	if company:
		conditions.append("COALESCE(slip.company, e.company) = %(company)s")
	if branches:
		conditions.append("e.branch IN %(branches)s")
	rows = frappe.db.sql(
		f"""
		SELECT slip.name, slip.employee, slip.year, slip.month,
		       slip.tong_thu_nhap, slip.thuc_linh,
		       slip.tong_thu_nhap_encrypted, slip.thuc_linh_encrypted,
		       COALESCE(items.allowance, 0) AS allowance
		FROM `tabVNT Salary Slip` slip
		LEFT JOIN `tabEmployee` e ON e.name = slip.employee
		LEFT JOIN (
			SELECT parent, SUM(COALESCE(tong, amount, 0)) AS allowance
			FROM `tabVNT Salary Slip Item`
			GROUP BY parent
		) items ON items.parent = slip.name
		WHERE {' AND '.join(conditions)}
		""",
		params,
		as_dict=True,
	)

	monthly = Counter()
	allowance_monthly = Counter()
	employees_by_month: dict[tuple[int, int], set[str]] = {}
	for row in rows:
		year = cint(row.get("year"))
		month = _month_number(row.get("month"))
		if not year or not month:
			continue
		gross, net_value = _salary_values(row)
		key = (year, month)
		monthly[key] += gross
		allowance_monthly[key] += _number(row.get("allowance"))
		employees_by_month.setdefault(key, set()).add(row.get("employee"))

	months = list(range(1, as_of_date.month + 1))
	labels = [_("Tháng {0}").format(month) for month in months]
	salary_values = [round(monthly[(as_of_date.year, month)]) for month in months]
	allowance_values = [round(allowance_monthly[(as_of_date.year, month)]) for month in months]
	previous_key = (previous_date.year, previous_date.month)
	previous_salary = monthly[previous_key]
	previous_employees = len(employees_by_month.get(previous_key, set()))
	ytd_salary = sum(monthly[(as_of_date.year, month)] for month in months)
	ytd_allowance = sum(allowance_monthly[(as_of_date.year, month)] for month in months)
	has_data = any(salary_values) or previous_salary > 0 or ytd_allowance > 0

	return {
		"available": True,
		"has_data": has_data,
		"message": "" if has_data else _("Chưa có bảng lương đã chốt trong phạm vi đang chọn."),
		"kpis": [
			{
				"id": "previous_month",
				"title": _("Tổng lương tháng {0}").format(previous_date.month),
				"value": round(previous_salary),
				"caption": _("Bảng lương đã chốt"),
			},
			{
				"id": "ytd_salary",
				"title": _("Lương từ đầu năm"),
				"value": round(ytd_salary),
				"caption": _("Đến tháng {0}").format(as_of_date.month),
			},
			{
				"id": "ytd_allowance",
				"title": _("Phụ cấp từ đầu năm"),
				"value": round(ytd_allowance),
				"caption": _("Theo bảng lương đã chốt"),
			},
			{
				"id": "average_salary",
				"title": _("Bình quân tháng {0}").format(previous_date.month),
				"value": round(previous_salary / previous_employees) if previous_employees else 0,
				"caption": _("Trên {0} nhân sự có bảng lương").format(previous_employees),
			},
		],
		"chart": {
			"labels": labels,
			"datasets": [
				{"name": _("Tổng lương"), "values": salary_values},
				{"name": _("Phụ cấp"), "values": allowance_values},
			],
		},
	}


def _build_branch_rows(snapshot: dict) -> list[dict]:
	chart = (snapshot.get("dimensions") or {}).get("branch") or {}
	labels = chart.get("labels") or []
	values = ((chart.get("datasets") or [{}])[0]).get("values") or []
	total = sum(_number(value) for value in values)
	rows = [
		{
			"label": label,
			"value": cint(values[index]) if index < len(values) else 0,
			"percentage": round((_number(values[index]) / total * 100), 1) if total and index < len(values) else 0,
		}
		for index, label in enumerate(labels)
	]
	return sorted(rows, key=lambda row: row["value"], reverse=True)


def _is_manager(employee: dict) -> bool:
	"""Use the governed designation group first, then the site's designation convention."""
	designation = (employee.get("designation") or "").casefold()
	return employee.get("custom_designation_group") in LEADERSHIP_GROUPS or any(
		marker in designation for marker in LEADERSHIP_DESIGNATION_MARKERS
	)


def _person_row(employee: dict, **values) -> dict:
	row = {
		"employee": employee.get("name"),
		"employee_name": employee.get("employee_name") or employee.get("name"),
		"designation": employee.get("designation") or "",
		"department": employee.get("department") or "",
		"branch": employee.get("branch") or "",
		"group": "manager" if _is_manager(employee) else "employee",
		"group_label": _("Quản lý") if _is_manager(employee) else _("Nhân viên"),
	}
	row.update(values)
	return row


def _split_people(rows: list[dict]) -> dict:
	managers = [row for row in rows if row.get("group") == "manager"]
	employees = [row for row in rows if row.get("group") != "manager"]
	return {
		"total": len(rows),
		"manager_count": len(managers),
		"employee_count": len(employees),
		"managers": managers,
		"employees": employees,
	}


def _get_attendance_map_for_date(the_date, employee_ids: tuple[str, ...]) -> dict:
	if not employee_ids:
		return {}
	rows = frappe.get_all(
		"Attendance",
		filters={
			"employee": ("in", list(employee_ids)),
			"attendance_date": the_date,
			"docstatus": ("<", 2),
		},
		fields=[
			"name",
			"employee",
			"status",
			"docstatus",
			"shift",
			"in_time",
			"out_time",
			"late_entry",
			"early_exit",
			"working_hours",
		],
		order_by="docstatus desc, modified desc",
		ignore_permissions=True,
	)
	result = {}
	for row in rows:
		result.setdefault(row.employee, row)
	return result


def _get_confirmation_people(the_date, employee_map: dict[str, dict]) -> dict:
	if not employee_map:
		return {
			"all": [],
			"needs_explanation": [],
			"awaiting_hr": [],
			"resolved": [],
			"item_count": 0,
		}
	rows = frappe.db.sql(
		"""
		SELECT p.employee, p.name AS confirmation, p.status AS confirmation_status,
		       i.name AS item, i.issue_code, i.issue_type, i.type AS explanation,
		       i.confirm, i.planned_shift, i.time_in, i.time_out
		FROM `tabVNT Attendance Confirm Item` i
		INNER JOIN `tabVNT Attendance Confirm` p ON p.name = i.parent
		WHERE p.docstatus < 2
		  AND i.date = %(date)s
		  AND p.employee IN %(employees)s
		ORDER BY p.employee_name, i.idx
		""",
		{"date": the_date, "employees": tuple(employee_map)},
		as_dict=True,
	)

	state_priority = {"needs_explanation": 0, "awaiting_hr": 1, "resolved": 2}
	grouped: dict[str, dict] = {}
	for source in rows:
		explanation = (source.get("explanation") or "").strip()
		decision = (source.get("confirm") or "").strip()
		state = "needs_explanation" if not explanation else ("awaiting_hr" if not decision else "resolved")
		current = grouped.get(source.employee)
		if not current:
			current = _person_row(
				employee_map[source.employee],
				state=state,
				confirmation=source.confirmation,
				issues=[],
			)
			grouped[source.employee] = current
		elif state_priority[state] < state_priority[current["state"]]:
			current["state"] = state
		current["issues"].append(
			{
				"item": source.item,
				"issue_code": source.issue_code or "",
				"issue_type": source.issue_type or _("Bất thường chấm công"),
				"planned_shift": source.planned_shift or "",
				"time_in": _format_time(source.time_in),
				"time_out": _format_time(source.time_out),
			}
		)

	all_people = list(grouped.values())
	all_people.sort(key=lambda row: (row["group"] != "manager", row["employee_name"]))
	return {
		"all": all_people,
		"needs_explanation": [row for row in all_people if row["state"] == "needs_explanation"],
		"awaiting_hr": [row for row in all_people if row["state"] == "awaiting_hr"],
		"resolved": [row for row in all_people if row["state"] == "resolved"],
		"item_count": len(rows),
	}


def _minutes_between(later, earlier) -> int:
	if not later or not earlier:
		return 0
	return max(int(ceil((get_datetime(later) - get_datetime(earlier)).total_seconds() / 60)), 0)


def _timing_summary(rows: list[dict]) -> dict:
	minutes = [cint(row.get("minutes")) for row in rows]
	return {
		"count": len(rows),
		"average_minutes": round(sum(minutes) / len(minutes)) if minutes else 0,
		"maximum_minutes": max(minutes, default=0),
	}


def _build_morning_briefing(as_of_date, employees_today: list[dict], employees_previous: list[dict]) -> dict:
	previous_date = as_of_date - timedelta(days=1)
	today_map = {row.name: row for row in employees_today}
	previous_map = {row.name: row for row in employees_previous}
	all_employee_map = {**previous_map, **today_map}
	all_employees = list(all_employee_map.values())

	windows = build_shift_windows(all_employees, previous_date, as_of_date) if all_employees else {}
	checkin_map, outside_map = load_checkins_for_windows(
		all_employees, windows, previous_date, as_of_date
	) if all_employees else ({}, {})
	holiday_context = load_holiday_context(
		all_employees, windows, previous_date, as_of_date
	) if all_employees else frappe._dict(company_lists={}, holidays={})
	observed_today = [
		get_datetime(row.time)
		for rows in [*checkin_map.values(), *outside_map.values()]
		for row in rows
		if get_datetime(row.time).date() == as_of_date
	]
	latest_checkin_at = max(observed_today, default=None)

	today_leave = _leave_map(as_of_date, tuple(today_map))
	today_trip = _trip_map(as_of_date, tuple(today_map))
	arrivals = []
	expected_today = 0
	for employee_id, employee in today_map.items():
		window = windows.get((employee_id, as_of_date))
		day_type = classify_work_date(employee, window, holiday_context)
		if (
			day_type == "work"
			and employee_id not in today_leave
			and employee_id not in today_trip
			and not cint(employee.get("custom_need_check"))
		):
			expected_today += 1

		planned_logs = sorted(
			checkin_map.get((employee_id, as_of_date), []), key=lambda row: get_datetime(row.time)
		)
		unplanned_logs = sorted(
			outside_map.get((employee_id, as_of_date), []), key=lambda row: get_datetime(row.time)
		)
		arrival_time = None
		arrival_source = ""
		if window and not window.is_off and planned_logs:
			details = calculate_attendance_details(window, planned_logs, respect_marking_flags=False)
			if details.has_in:
				arrival_time = details.in_time or planned_logs[0].time
				arrival_source = _("Trong ca")
		if not arrival_time:
			candidate = next(
				(row for row in unplanned_logs if (row.get("log_type") or "IN") != "OUT"),
				None,
			)
			if candidate:
				arrival_time = candidate.time
				arrival_source = _("Ngoài ca")
		if arrival_time:
			arrivals.append(
				_person_row(
					employee,
					first_in=_format_time(arrival_time),
					planned_shift=(window.shift_type if window and not window.is_off else ""),
					arrival_source=arrival_source,
				)
			)
	arrivals.sort(key=lambda row: (row["group"] != "manager", row.get("first_in") or "", row["employee_name"]))
	arrival_data = _split_people(arrivals)
	arrival_data["expected"] = expected_today

	previous_leave = _leave_map(previous_date, tuple(previous_map))
	previous_trip = _trip_map(previous_date, tuple(previous_map))
	attendance_map = _get_attendance_map_for_date(previous_date, tuple(previous_map))
	absent_rows = []
	late_rows = []
	early_rows = []
	scheduled_count = 0
	for employee_id, employee in previous_map.items():
		window = windows.get((employee_id, previous_date))
		if classify_work_date(employee, window, holiday_context) != "work" or not window or window.is_off:
			continue
		scheduled_count += 1
		if employee_id in previous_leave or employee_id in previous_trip:
			continue

		logs = sorted(
			checkin_map.get((employee_id, previous_date), []), key=lambda row: get_datetime(row.time)
		)
		outside_logs = sorted(
			outside_map.get((employee_id, previous_date), []), key=lambda row: get_datetime(row.time)
		)
		details = calculate_attendance_details(window, logs, respect_marking_flags=False) if logs else None
		attendance = attendance_map.get(employee_id)
		is_absent = False
		absence_source = ""
		if attendance and attendance.docstatus == 1:
			is_absent = attendance.status == "Absent"
			absence_source = _("Attendance đã chốt")
		elif attendance:
			is_absent = attendance.status == "Absent"
			absence_source = _("Attendance nháp")
		elif not cint(employee.get("custom_need_check")):
			is_absent = not details or details.status == "Absent"
			absence_source = _("Tạm tính từ ca và log máy")
		if is_absent:
			absent_rows.append(
				_person_row(
					employee,
					planned_shift=window.shift_type or "",
					in_time=_format_time(details.in_time if details else None),
					out_time=_format_time(details.out_time if details else None),
					source=absence_source,
					finalized=bool(attendance and attendance.docstatus == 1),
				)
			)

		if details and details.has_in and details.late_entry:
			late_rows.append(
				_person_row(
					employee,
					planned_shift=window.shift_type or "",
					actual_time=_format_time(details.in_time),
					planned_time=_format_time(window.start_datetime),
					minutes=_minutes_between(details.in_time, window.start_datetime),
				)
			)
		if details and details.has_in and details.has_out and details.status == "Present" and details.early_exit:
			later_outside_out = next(
				(
					row
					for row in reversed(outside_logs)
					if (row.get("log_type") or "").upper() == "OUT"
					and get_datetime(row.time) > get_datetime(details.out_time)
				),
				None,
			)
			early_rows.append(
				_person_row(
					employee,
					planned_shift=window.shift_type or "",
					actual_time=_format_time(details.out_time),
					planned_time=_format_time(window.end_datetime),
					minutes=_minutes_between(window.end_datetime, details.out_time),
					outside_out_time=_format_time(later_outside_out.time) if later_outside_out else "",
				)
			)

	absent_rows.sort(key=lambda row: (not row["finalized"], row["group"] != "manager", row["employee_name"]))
	late_rows.sort(key=lambda row: (-row["minutes"], row["group"] != "manager", row["employee_name"]))
	early_rows.sort(key=lambda row: (-row["minutes"], row["group"] != "manager", row["employee_name"]))
	confirmations = _get_confirmation_people(previous_date, previous_map)

	birthdays = []
	for employee in employees_today:
		date_of_birth = employee.get("date_of_birth")
		if date_of_birth and (getdate(date_of_birth).month, getdate(date_of_birth).day) == (as_of_date.month, as_of_date.day):
			birthdays.append(_person_row(employee))
	birthdays.sort(key=lambda row: (row["group"] != "manager", row["employee_name"]))
	birthday_data = _split_people(birthdays)

	finalized_absent = sum(1 for row in absent_rows if row["finalized"])
	provisional_absent = len(absent_rows) - finalized_absent
	late_summary = _timing_summary(late_rows)
	early_summary = _timing_summary(early_rows)
	early_summary["outside_out_count"] = sum(
		1 for row in early_rows if row.get("outside_out_time")
	)
	needs_explanation = confirmations["needs_explanation"]

	return {
		"as_of_date": str(as_of_date),
		"previous_date": str(previous_date),
		"latest_checkin_at": str(latest_checkin_at) if latest_checkin_at else "",
		"kpis": [
			{
				"id": "arrived_today",
				"title": _("Đã đến công ty hôm nay"),
				"value": arrival_data["total"],
				"caption": _("{0} quản lý · {1} nhân viên").format(
					arrival_data["manager_count"], arrival_data["employee_count"]
				),
				"tone": "green",
				"target": "arrivals",
			},
			{
				"id": "absent_yesterday",
				"title": _("Vắng hôm qua"),
				"value": len(absent_rows),
				"caption": _("{0} đã chốt · {1} tạm tính").format(finalized_absent, provisional_absent),
				"tone": "red",
				"target": "yesterday-absent",
			},
			{
				"id": "explanation_yesterday",
				"title": _("Cần giải trình hôm qua"),
				"value": len(needs_explanation),
				"caption": _("{0} chờ HR xác nhận").format(len(confirmations["awaiting_hr"])),
				"tone": "amber",
				"target": "yesterday-explanation",
			},
			{
				"id": "late_yesterday",
				"title": _("Đi muộn hôm qua"),
				"value": late_summary["count"],
				"caption": _("TB {0} phút · cao nhất {1} phút").format(
					late_summary["average_minutes"], late_summary["maximum_minutes"]
				),
				"tone": "violet",
				"target": "yesterday-late",
			},
			{
				"id": "early_yesterday",
				"title": _("Về sớm cần đối soát hôm qua"),
				"value": early_summary["count"],
				"caption": (
					_("TB {0} phút · {1} có OUT ngoài ca").format(
						early_summary["average_minutes"], early_summary["outside_out_count"]
					)
					if early_summary["outside_out_count"]
					else _("TB {0} phút · cao nhất {1} phút").format(
						early_summary["average_minutes"], early_summary["maximum_minutes"]
					)
				),
				"tone": "pink",
				"target": "yesterday-early",
			},
			{
				"id": "birthdays_today",
				"title": _("Sinh nhật hôm nay"),
				"value": birthday_data["total"],
				"caption": _("{0} quản lý · {1} nhân viên").format(
					birthday_data["manager_count"], birthday_data["employee_count"]
				),
				"tone": "blue",
				"target": "birthdays",
			},
		],
		"arrivals": arrival_data,
		"birthdays": birthday_data,
		"yesterday": {
			"date": str(previous_date),
			"scheduled": scheduled_count,
			"absent": absent_rows,
			"absent_finalized": finalized_absent,
			"absent_provisional": provisional_absent,
			"explanations": needs_explanation,
			"awaiting_hr": confirmations["awaiting_hr"],
			"resolved_explanations": confirmations["resolved"],
			"explanation_item_count": confirmations["item_count"],
			"late": late_rows,
			"early": early_rows,
			"late_summary": late_summary,
			"early_summary": early_summary,
		},
	}


def _build_snapshot(as_of_date, company: str, branches: tuple[str, ...], branch_options: tuple[str, ...]) -> dict:
	previous_date = as_of_date - timedelta(days=1)
	employees_today = _get_scoped_employees(as_of_date, company, branches)
	employees_previous = _get_scoped_employees(previous_date, company, branches)
	morning = _build_morning_briefing(as_of_date, employees_today, employees_previous)

	return {
		"scope": {
			"as_of_date": str(as_of_date),
			"company": company,
			"branches": list(branches),
			"branch_options": list(branch_options),
			"label": _("Tất cả chi nhánh") if not branches else ", ".join(branches),
		},
		"kpis": morning["kpis"],
		"morning": morning,
		"context": {
			"generated_at": str(now_datetime()),
			"latest_checkin_at": morning["latest_checkin_at"],
			"timezone": frappe.utils.get_system_timezone(),
			"manager_definition": _(
				"Quản lý được xác định theo Nhóm chức danh hoặc chức danh quản lý đã cấu hình."
			),
			"sources": [
				"Employee",
				"Shift Assignment",
				"VNT Shift Group",
				"Employee Checkin",
				"Attendance",
				"Leave Application",
				"VNT Business Trip Request",
				"VNT Attendance Confirm",
			],
		},
	}


@redis_cache(ttl=30)
def _cached_snapshot(user: str, as_of_date: str, company: str, branches_json: str, options_json: str) -> dict:
	# ``user`` is part of the key because salary visibility is permission-sensitive.
	return _build_snapshot(
		getdate(as_of_date),
		company,
		tuple(json.loads(branches_json)),
		tuple(json.loads(options_json)),
	)


@frappe.whitelist()
def get_leadership_snapshot(as_of_date=None, branches=None, branch=None, company=None, force: int = 0):
	"""Return one coherent, permission-aware snapshot for every dashboard block."""
	date_value, company_value, branch_values, branch_options = _resolve_scope(
		as_of_date=as_of_date,
		branches=branches,
		branch=branch,
		company=company,
	)
	if cint(force):
		_cached_snapshot.clear_cache()
	return _cached_snapshot(
		frappe.session.user,
		str(date_value),
		company_value,
		json.dumps(list(branch_values), ensure_ascii=False),
		json.dumps(list(branch_options), ensure_ascii=False),
	)


def clear_cache():
	_cached_snapshot.clear_cache()
