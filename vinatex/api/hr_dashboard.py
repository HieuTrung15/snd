"""Data API for the Human Resources workspace dashboard."""

from __future__ import annotations

import re
from collections import Counter

import frappe
from frappe import _
from frappe.utils import get_first_day, getdate, today


AGE_BUCKETS = (
	"Dưới 25 tuổi",
	"25-34 tuổi",
	"35-44 tuổi",
	"45-54 tuổi",
	"55 tuổi trở lên",
)
SENIORITY_BUCKETS = (
	"Dưới 1 năm",
	"1-3 năm",
	"3-5 năm",
	"5-10 năm",
	"Trên 10 năm",
)
GENERAL_EDUCATION_MISSING_LABEL = "Chưa cập nhật"
DESIGNATION_GROUP_FALLBACKS = {
	"Giám đốc": "Lãnh đạo Chi nhánh",
	"Phó giám đốc": "Lãnh đạo Chi nhánh",
	"Trưởng phòng": "Quản lý cấp trung",
	"Phó phòng": "Quản lý cấp trung",
	"Trưởng ca": "Quản lý cấp cơ sở",
	"Phó trưởng ca": "Quản lý cấp cơ sở",
	"Trưởng công đoạn": "Quản lý cấp cơ sở",
	"Phó công đoạn": "Quản lý cấp cơ sở",
	"Nhân viên văn phòng": "Nhân viên",
	"Thủ kho": "Nhân viên",
	"Lái xe": "Nhân viên",
	"Nhân viên bếp ăn": "Nhân viên",
	"Công nhân công đoạn": "Công nhân",
	"Công nhân đi ca": "Công nhân",
}


def _resolve_as_of_date(value=None):
	as_of_date = getdate(value or today())
	if as_of_date > getdate(today()):
		frappe.throw(_("Ngày dữ liệu không được lớn hơn ngày hiện tại."))
	return as_of_date


def _normalize_branches(value):
	if not value:
		return ()
	if isinstance(value, str):
		try:
			parsed = frappe.parse_json(value)
		except (TypeError, ValueError):
			parsed = value
		value = parsed if isinstance(parsed, (list, tuple, set)) else [parsed]
	return tuple(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _active_conditions(as_of_date, branches=None, company=None):
	conditions = []
	params = {"as_of_date": as_of_date}

	# Current figures stay aligned with ERPNext's authoritative status. Historical
	# snapshots are reconstructed from the employee's joining/relieving dates.
	if as_of_date == getdate(today()):
		conditions.append("e.status = 'Active'")
	else:
		conditions.append("e.date_of_joining <= %(as_of_date)s")
		conditions.append("(e.relieving_date IS NULL OR e.relieving_date > %(as_of_date)s)")

	if branches:
		conditions.append("e.branch IN %(branches)s")
		params["branches"] = branches
	if company:
		conditions.append("e.company = %(company)s")
		params["company"] = company

	return conditions, params


def _age_bucket(age):
	if age < 25:
		return AGE_BUCKETS[0]
	if age < 35:
		return AGE_BUCKETS[1]
	if age < 45:
		return AGE_BUCKETS[2]
	if age < 55:
		return AGE_BUCKETS[3]
	return AGE_BUCKETS[4]


def _seniority_bucket(years):
	if years < 1:
		return SENIORITY_BUCKETS[0]
	if years < 3:
		return SENIORITY_BUCKETS[1]
	if years < 5:
		return SENIORITY_BUCKETS[2]
	if years < 10:
		return SENIORITY_BUCKETS[3]
	return SENIORITY_BUCKETS[4]


def _chart_data(counts, order=None, dataset_name="Nhân sự"):
	labels = [label for label in (order or counts.keys()) if counts.get(label)]
	return {
		"labels": labels,
		"datasets": [{"name": dataset_name, "values": [int(counts[label]) for label in labels]}],
	}


def _normalize_general_education(value):
	"""Normalize the free-text Employee.general education value for grouping."""
	value = " ".join(str(value or "").split())
	if not value:
		return GENERAL_EDUCATION_MISSING_LABEL

	# Treat spacing and leading-zero variants of the common grade format equally,
	# while preserving any other value entered by HR instead of guessing its meaning.
	grade = re.fullmatch(r"(\d{1,2})\s*/\s*(\d{1,2})", value)
	if grade:
		return f"{int(grade.group(1))}/{int(grade.group(2))}"
	return value


def _general_education_sort_key(item):
	label, count = item
	if label == GENERAL_EDUCATION_MISSING_LABEL:
		return (2, 0, 0, label)
	grade = re.fullmatch(r"(\d{1,2})/(\d{1,2})", label)
	if grade:
		return (0, -int(grade.group(2)), -int(grade.group(1)), label)
	return (1, -int(count), 0, label.casefold())


def _get_general_education_counts(conditions, params):
	"""Count active employees by Employee.custom_general_education."""
	rows = frappe.db.sql(
		f"""
			SELECT e.custom_general_education
			FROM `tabEmployee` e
			WHERE {" AND ".join(conditions)}
		""",
		params,
		as_dict=True,
	)
	counts = Counter(_normalize_general_education(row.custom_general_education) for row in rows)
	return Counter(dict(sorted(counts.items(), key=_general_education_sort_key)))


@frappe.whitelist()
def get_employee_branches(company=None):
	"""Return distinct, readable Employee branches for the HR workspace filter."""
	if not frappe.has_permission("Employee", "read"):
		frappe.throw(_("Bạn không có quyền xem dữ liệu nhân sự."), frappe.PermissionError)

	company = (company or "").strip()
	filters = {"branch": ["is", "set"]}
	if company:
		filters["company"] = company

	rows = frappe.get_list(
		"Employee",
		fields=["branch"],
		filters=filters,
		group_by="branch",
		order_by="branch asc",
		limit_page_length=0,
	)
	return [row.branch for row in rows if row.branch]


@frappe.whitelist()
def get_hr_dashboard_snapshot(as_of_date=None, branches=None, branch=None, company=None):
	"""Return KPI and employee distributions as they stood on one date."""
	if not frappe.has_permission("Employee", "read"):
		frappe.throw(_("Bạn không có quyền xem dữ liệu nhân sự."), frappe.PermissionError)

	as_of_date = _resolve_as_of_date(as_of_date)
	branches = _normalize_branches(branches or branch)
	company = (company or "").strip()
	conditions, params = _active_conditions(as_of_date, branches, company)

	employees = frappe.db.sql(
		f"""
			SELECT
				e.name,
				e.branch,
				COALESCE(
					NULLIF(TRIM(d.department_name), ''),
					NULLIF(TRIM(e.department), '')
				) AS department,
				e.gender,
				e.employment_type,
				e.custom_designation_group,
				e.designation,
				TIMESTAMPDIFF(YEAR, e.date_of_birth, %(as_of_date)s) AS age,
				TIMESTAMPDIFF(MONTH, e.date_of_joining, %(as_of_date)s) AS seniority_months
			FROM `tabEmployee` e
			LEFT JOIN `tabDepartment` d ON d.name = e.department
			WHERE {" AND ".join(conditions)}
		""",
		params,
		as_dict=True,
	)

	counts = {
		"designation": Counter(),
		"designation_group": Counter(),
		"department": Counter(),
		"age": Counter(),
		"seniority": Counter(),
		"employment_type": Counter(),
		"branch": Counter(),
		"gender": Counter(),
	}
	ages = []
	for employee in employees:
		designation = str(employee.designation or "").strip() or "Chưa xác định"
		designation_group = (
			str(employee.custom_designation_group or "").strip()
			or DESIGNATION_GROUP_FALLBACKS.get(designation)
			or "Chưa xác định"
		)
		department = str(employee.department or "").strip() or "Chưa xác định"
		counts["designation"][designation] += 1
		counts["designation_group"][designation_group] += 1
		counts["department"][department] += 1
		counts["employment_type"][employee.employment_type or "Chưa xác định"] += 1
		counts["branch"][employee.branch or "Chưa xác định"] += 1
		counts["gender"][employee.gender or "Chưa xác định"] += 1
		if employee.age is not None and employee.age >= 0:
			ages.append(int(employee.age))
			counts["age"][_age_bucket(int(employee.age))] += 1
		if employee.seniority_months is not None and employee.seniority_months >= 0:
			counts["seniority"][_seniority_bucket(employee.seniority_months / 12)] += 1

	month_start = get_first_day(as_of_date)
	common_filters = {
		**({"branch": ["in", list(branches)]} if branches else {}),
		**({"company": company} if company else {}),
	}
	new_count = frappe.db.count(
		"Employee",
		filters={"date_of_joining": ["between", [month_start, as_of_date]], **common_filters},
	)
	left_count = frappe.db.count(
		"Employee",
		filters={"relieving_date": ["between", [month_start, as_of_date]], **common_filters},
	)

	general_education_counts = _get_general_education_counts(conditions, params)
	return {
		"as_of_date": str(as_of_date),
		"kpis": {
			"active": len(employees),
			"new": int(new_count or 0),
			"left": int(left_count or 0),
			"average_age": round(sum(ages) / len(ages), 1) if ages else 0,
		},
		"dimensions": {
			"designation": _chart_data(counts["designation"]),
			"designation_group": _chart_data(counts["designation_group"]),
			"department": _chart_data(counts["department"]),
			"age": _chart_data(counts["age"], AGE_BUCKETS),
			"seniority": _chart_data(counts["seniority"], SENIORITY_BUCKETS),
			"education": _chart_data(general_education_counts),
			"employment_type": _chart_data(counts["employment_type"]),
			"branch": _chart_data(counts["branch"]),
			"gender": _chart_data(counts["gender"]),
		},
	}
