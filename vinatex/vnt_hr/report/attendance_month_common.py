from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from dataclasses import dataclass
from typing import Dict, Optional

import frappe
from frappe.utils import add_days, cint, getdate, today

from vinatex.vnt_hr.report.tổng_hợp_chấm_công_tháng.tổng_hợp_chấm_công_tháng import (
	STATUS_CODE,
	_attendance_map,
	_holiday_map,
	_is_attendance_business_trip,
	_is_weekend,
	_leave_map,
	_leave_type_group_map,
	_categorize_leave,
)


@frappe.whitelist()
def get_employee_for_user():
	"""Return the Employee mapped to the current user, if any."""
	user = frappe.session.user
	if not user or user == "Guest":
		return None

	employee = frappe.get_value(
		"Employee",
		{"user_id": user, "status": "Active"},
		"name",
		ignore_permissions=True,
	)
	if not employee:
		return None

	return {"employee": employee}


@dataclass(frozen=True)
class DayDetail:
	date: object
	status: str
	status_key: Optional[str]
	is_future: bool
	is_half_day: bool
	half_day_reason: Optional[str]
	business_trip_units: float
	leave_units: float
	leave_category: Optional[str]
	leave_type: Optional[str]
	attendance_status: Optional[str]
	source: Optional[str]


def _daterange(start_date, end_date):
	current = start_date
	while current <= end_date:
		yield current
		current += timedelta(days=1)


def fetch_employee_doc(employee: str) -> Optional[dict]:
	fields = [
		"name",
		"employee_name",
		"department",
		"company",
		"holiday_list",
		"date_of_joining",
		"relieving_date",
		"custom_need_check",
		"designation",
	]
	return frappe.db.get_value("Employee", employee, fields, as_dict=True)


def compute_employee_month_context(
	employee_doc: dict,
	start_date,
	end_date,
	company: Optional[str] = None,
) -> Dict[str, object]:
	"""
	Build daily status map and summary metrics for an employee in the given period,
	re-using the same logic as the Tổng hợp chấm công tháng report.
	"""
	if not employee_doc:
		return {}

	employee = employee_doc["name"]
	company = company or employee_doc.get("company")

	days = list(_daterange(start_date, end_date))
	today_date = getdate(add_days(today(), -1))
	effective_end_date = min(end_date, today_date)
	data_days = [d for d in days if d <= effective_end_date]

	if data_days and company:
		emp_ref = {
			"name": employee,
			"holiday_list": employee_doc.get("holiday_list"),
			"custom_need_check": employee_doc.get("custom_need_check"),
			"date_of_joining": employee_doc.get("date_of_joining"),
			"relieving_date": employee_doc.get("relieving_date"),
			"designation": employee_doc.get("designation"),
		}
		holi_map = _holiday_map([emp_ref], company, data_days[0], data_days[-1])
		att_map = _attendance_map([emp_ref], data_days[0], data_days[-1])
		leave_map = _leave_map([emp_ref], data_days[0], data_days[-1])
	else:
		holi_map = {}
		att_map = {}
		leave_map = {}

	leave_type_groups = _leave_type_group_map()
	totals = {
		"tot_present": 0,
		"tot_leave": 0,
		"tot_holiday": 0,
		"tot_weekend": 0,
		"tot_business_trip": 0.0,
		"tot_absent": 0,
		"tot_miss": 0,
		"tot_not_joined": 0,
		"tot_half_day": 0,
	}
	category_totals = defaultdict(float)
	day_details: Dict[object, DayDetail] = {}
	value_units = 0.0

	doj_raw = employee_doc.get("date_of_joining")
	doj = getdate(doj_raw) if doj_raw else None
	manual_flag = bool(cint(employee_doc.get("custom_need_check")))

	for day in days:
		is_future = day > effective_end_date
		status = ""
		status_key = None
		is_half_day = False
		half_day_reason = None
		business_trip_units = 0.0
		leave_units = 0.0
		leave_category = None
		leave_type = None
		attendance_status = None
		source = None

		if is_future:
			status_key = "future"
		else:
			key = (employee, day)
			
			if doj and day < doj:
				status = STATUS_CODE["CHƯA VÀO LÀM"]
				status_key = "pre_join"
				source = "pre_join"
				totals["tot_not_joined"] += 1
			elif key in holi_map:
				status = STATUS_CODE["NGHỈ LỄ"]
				status_key = "holiday"
				source = "holiday"
				totals["tot_holiday"] += 1
			elif _is_weekend(day):
				status = STATUS_CODE["CUỐI TUẦN"]
				status_key = "weekend"
				source = "weekend"
				totals["tot_weekend"] += 1
			else:
				att = att_map.get(key)
				if att:
					# frappe.throw(att.get("status"))
					att_status = (att.get("status") or "").strip()
					leave_type = att.get("leave_type")
					attendance_status = att_status
					leave_group = leave_type_groups.get(leave_type)
					if att_status in ("Present", "Work From Home", "Work From Office"):
						status = STATUS_CODE["ĐI LÀM"]
						status_key = "present"
						source = "attendance_present"
						totals["tot_present"] += 1
						value_units += 1.0
						print(value_units)
					elif att_status in ("Work Trip",):
						units = 1.0
						status = STATUS_CODE["CÔNG TÁC"]
						status_key = "business_trip"
						source = "attendance_work_trip"
						business_trip_units = units
						totals["tot_business_trip"] += units
						category_totals["business_trip"] += units
						value_units += units
					elif att_status in ("On Leave",):
						units = 1.0
						if _is_attendance_business_trip(leave_type):
							status = STATUS_CODE["CÔNG TÁC"]
							status_key = "business_trip"
							source = "attendance_leave_trip"
							business_trip_units = units
							totals["tot_business_trip"] += units
							category_totals["business_trip"] += units
							value_units += units
						else:
							status = STATUS_CODE["NGHỈ PHÉP"]
							status_key = "leave_full"
							source = "attendance_leave"
							leave_units = units
							leave_type = att.get("leave_type")
							category = _categorize_leave(leave_type, leave_group)
							leave_category = category
							category_totals[category] += units
							totals["tot_leave"] += 1
					elif att_status in ("Half Day",):
						status = STATUS_CODE["NGHỈ NỬA NGÀY"]
						status_key = "half_day"
						source = "attendance_half_day"
						is_half_day = True
						half_day_reason = "attendance"
						totals["tot_half_day"] += 1
						value_units += 0.5
					elif att_status in ("Absent",):
						status = STATUS_CODE["VẮNG MẶT"]
						status_key = "absent"
						source = "attendance_absent"
						totals["tot_absent"] += 1
					else:
						status = STATUS_CODE["VẮNG MẶT"]
						status_key = "absent"
						source = "attendance_other"
						totals["tot_absent"] += 1
				else:
					leave = leave_map.get(key)
					if leave:
						units = 0.5 if leave.get("half_day") else 1.0
						leave_type = leave.get("leave_type")
						attendance_status = None
						leave_group = leave.get("leave_group") or leave_type_groups.get(leave_type)
						category = _categorize_leave(leave_type, leave_group)
						leave_category = category
						leave_units = units
						category_totals[category] += units

						if category == "business_trip":
							status = STATUS_CODE["CÔNG TÁC"]
							status_key = "business_trip"
							source = "leave_business_trip"
							business_trip_units = units
							totals["tot_business_trip"] += units
							value_units += units
						elif leave.get("half_day"):
							status = STATUS_CODE["NGHỈ NỬA NGÀY"]
							status_key = "half_day"
							source = "leave_half_day"
							is_half_day = True
							half_day_reason = "leave"
							totals["tot_half_day"] += 1
						else:
							status = STATUS_CODE["NGHỈ PHÉP"]
							status_key = "leave_full"
							source = "leave_full"
							totals["tot_leave"] += 1
					else:
						status = STATUS_CODE["CHẤM CÔNG BẤT THƯỜNG"]
						status_key = "missing"
						source = "missing"
						totals["tot_miss"] += 1

		day_details[day] = DayDetail(
			date=day,
			status=status,
			status_key=status_key,
			is_future=is_future,
			is_half_day=is_half_day,
			half_day_reason=half_day_reason,
			business_trip_units=business_trip_units,
			leave_units=leave_units,
			leave_category=leave_category,
			leave_type=leave_type,
			attendance_status=attendance_status,
			source=source,
		)

	# if manual_flag:
	# 	for key in totals:
	# 		totals[key] = None
	# 	category_totals = {}
	# 	value_units = None
	# else:
	category_totals = dict(category_totals)

	return {
		"days": days,
		"effective_end_date": effective_end_date,
		"day_details": day_details,
		"totals": totals,
		"category_totals": category_totals,
		"value_units": value_units,
		"manual_flag": manual_flag,
		"employee": employee_doc,
	}
