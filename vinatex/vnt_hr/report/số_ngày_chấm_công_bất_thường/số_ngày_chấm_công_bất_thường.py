# -*- coding: utf-8 -*-
import json
from datetime import timedelta

import frappe
from frappe.utils import cint, get_first_day, get_last_day, getdate, today

SUMMARY_COLUMNS = [
    {"fieldname": "tot_abnormal", "label": "Ngày bất thường", "fieldtype": "Float", "width": 130},
    {"fieldname": "tot_present", "label": "Có Attendance", "fieldtype": "Int", "width": 120},
    {"fieldname": "tot_leave_full", "label": "Nghỉ (cả ngày)", "fieldtype": "Int", "width": 100},
    {"fieldname": "tot_leave_half", "label": "Nghỉ (nửa ngày)", "fieldtype": "Float", "width": 110},
    {"fieldname": "tot_holiday", "label": "Holiday", "fieldtype": "Int", "width": 90},
    {"fieldname": "tot_not_joined", "label": "Chưa vào làm", "fieldtype": "Int", "width": 120},
]

STATUS_PRIORITY = {
    "CV": 0,
    "L": 1,
    "X": 2,
    "NP": 3,
    "NP(0.5)": 4,
    "T": 5,
    "BT": 6,
    "BT(0.5)": 7,
}


def execute(filters=None):
    """
    Báo cáo số ngày chấm công bất thường (chỉ tính cho 1 nhân viên).
    - Giữ cột đầu tiên 'value' để Number Card có thể đọc được tổng ngày bất thường.
    - Bảng hiển thị từng ngày với các mã:
        * BT / BT(0.5): ngày bất thường (full hoặc nửa ngày)
        * X: có Attendance
        * NP / NP(0.5): nghỉ phép full / nửa ngày
        * L: Holiday
        * CV: trước ngày vào làm
    - Half-day leave -> hiển thị NP(0.5)/BT(0.5) và cộng 0.5 ngày bất thường.
    """

    filters = _parse_filters(filters)

    employee = filters.get("employee") or _employee_from_session()
    if not employee:
        return _columns(), [{"value": 0.0}], None

    start_date, end_date = _resolve_period(filters)
    if cint(filters.get("to_today") or 0):
        end_date = min(end_date, getdate(today()))
    if end_date < start_date:
        return _columns(), [{"value": 0.0}], None

    emp_doc = _get_employee_doc(employee)
    days = list(_daterange(start_date, end_date))

    holiday_days, weekend_days = _holiday_days(emp_doc, start_date, end_date)
    attendance_days = _attendance_days(employee, start_date, end_date)
    leave_map = _leave_map(employee, start_date, end_date)

    columns = _columns() + _info_columns() + _day_columns(days) + SUMMARY_COLUMNS

    totals = {col["fieldname"]: 0.0 for col in SUMMARY_COLUMNS}
    row = {
        "employee": employee,
        "employee_name": emp_doc.get("employee_name") if emp_doc else employee,
        "department": emp_doc.get("department") if emp_doc else None,
        "company": emp_doc.get("company") if emp_doc else None,
    }

    total_abnormal = 0.0

    for day in days:
        entries = _classify_day(day, emp_doc, holiday_days, weekend_days, attendance_days, leave_map)
        fieldname = f"d{day.day:02d}"
        if not entries:
            row[fieldname] = ""
            continue

        labels = []
        for entry in entries:
            labels.append(entry["code"])
            summary_field = entry.get("summary_field")
            fraction = entry.get("fraction", 1.0)
            if summary_field in totals:
                totals[summary_field] += fraction
            if entry.get("is_abnormal"):
                total_abnormal += fraction

        row[fieldname] = "/".join(labels)

    for key, value in totals.items():
        if key in {"tot_present", "tot_holiday", "tot_leave_full", "tot_not_joined"}:
            row[key] = int(value)
        else:
            row[key] = float(value)

    row["value"] = float(total_abnormal)

    return columns, [row], None


def _columns():
    return [{
        "label": "Số ngày chấm công bất thường",
        "fieldname": "value",
        "fieldtype": "Float",
        "width": 200,
    }]


def _info_columns():
    return [
        {
            "label": "Mã NV",
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 110,
        },
        {
            "label": "Tên nhân viên",
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": "Phòng ban",
            "fieldname": "department",
            "fieldtype": "Link",
            "options": "Department",
            "width": 150,
        },
        {
            "label": "Công ty",
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
            "width": 160,
        },
    ]


def _day_columns(days):
    return [
        {
            "label": f"{d.day:02d}",
            "fieldname": f"d{d.day:02d}",
            "fieldtype": "Data",
            "width": 55,
        }
        for d in days
    ]


def _parse_filters(filters):
    if isinstance(filters, str):
        try:
            filters = frappe.parse_json(filters)
        except Exception:
            try:
                filters = json.loads(filters)
            except Exception:
                filters = {}
    return filters or {}


def _employee_from_session():
    row = frappe.db.sql(
        """
        SELECT name FROM `tabEmployee`
        WHERE user_id = %s AND status = 'Active'
        LIMIT 1
        """,
        (frappe.session.user,),
    )
    return row[0][0] if row else None


def _resolve_period(filters):
    if filters.get("from_date") and filters.get("to_date"):
        return getdate(filters["from_date"]), getdate(filters["to_date"])

    ref_date = getdate(today())
    month = cint(filters.get("month") or 0)
    year = cint(filters.get("year") or 0)
    if month and year:
        start = get_first_day(getdate(f"{year:04d}-{month:02d}-01"))
    else:
        start = get_first_day(ref_date)
    end = get_last_day(start)
    end = min(end, ref_date)  # giữ hành vi cũ: không vượt quá hôm nay
    return start, end


def _get_employee_doc(employee):
    return frappe.db.get_value(
        "Employee",
        employee,
        ["employee_name", "department", "company", "date_of_joining", "holiday_list"],
        as_dict=True,
    ) or {}


def _daterange(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _holiday_days(emp_doc, start_date, end_date):
    holiday_list = emp_doc.get("holiday_list")
    company = emp_doc.get("company")
    if not holiday_list and company:
        holiday_list = frappe.db.get_value("Company", company, "default_holiday_list")
    if not holiday_list:
        return set(), set()

    rows = frappe.db.sql(
        """
        SELECT holiday_date, COALESCE(weekly_off, 0) AS weekly_off
        FROM `tabHoliday`
        WHERE parent = %(holiday_list)s
          AND holiday_date BETWEEN %(start)s AND %(end)s
    """,
        {"holiday_list": holiday_list, "start": start_date, "end": end_date},
        as_dict=True,
    )

    holidays = set()
    weekend_days = set()
    for r in rows:
        day = getdate(r.holiday_date)
        if cint(r.weekly_off):
            weekend_days.add(day)
        else:
            holidays.add(day)
    return holidays, weekend_days


def _attendance_days(employee, start_date, end_date):
    rows = frappe.db.sql(
        """
        SELECT attendance_date
        FROM `tabAttendance`
        WHERE employee = %(employee)s
          AND docstatus = 1
          AND attendance_date BETWEEN %(start)s AND %(end)s
    """,
        {"employee": employee, "start": start_date, "end": end_date},
        as_dict=True,
    )
    return {getdate(r.attendance_date) for r in rows}


def _leave_map(employee, start_date, end_date):
    rows = frappe.db.sql(
        """
        SELECT from_date, to_date, half_day, half_day_date
        FROM `tabLeave Application`
        WHERE employee = %(employee)s
          AND docstatus = 1
          AND status = 'Approved'
          AND to_date   >= %(start)s
          AND from_date <= %(end)s
    """,
        {"employee": employee, "start": start_date, "end": end_date},
        as_dict=True,
    )

    out = {}
    for row in rows:
        start = max(getdate(row.from_date), start_date)
        end = min(getdate(row.to_date), end_date)
        half_day_date = getdate(row.half_day_date) if row.half_day and row.half_day_date else None

        current = start
        while current <= end:
            fraction = 0.5 if half_day_date and current == half_day_date else 1.0
            out[current] = {"fraction": fraction}
            current += timedelta(days=1)
    return out


def _classify_day(day, emp_doc, holiday_days, weekend_days, attendance_days, leave_map):
    entries = []
    doj = emp_doc.get("date_of_joining")
    doj = getdate(doj) if doj else None

    if doj and day < doj:
        entries.append({
            "code": "CV",
            "summary_field": "tot_not_joined",
            "fraction": 1.0,
        })
        return entries

    if day in holiday_days:
        entries.append({
            "code": "L",
            "summary_field": "tot_holiday",
            "fraction": 1.0,
        })
        return entries

    if day in attendance_days:
        entries.append({
            "code": "X",
            "summary_field": "tot_present",
            "fraction": 1.0,
        })
        return entries

    if day in weekend_days:
        entries.append({
            "code": "T",
            "fraction": 0.0,
        })
        return entries

    leave = leave_map.get(day)
    if leave:
        fraction = leave["fraction"]
        if fraction >= 1:
            entries.append({
                "code": "NP",
                "summary_field": "tot_leave_full",
                "fraction": 1.0,
            })
            return entries

        # half-day leave + 0.5 abnormal
        entries.append({
            "code": "NP(0.5)",
            "summary_field": "tot_leave_half",
            "fraction": 0.5,
        })
        entries.append({
            "code": "BT(0.5)",
            "summary_field": "tot_abnormal",
            "fraction": 0.5,
            "is_abnormal": True,
        })
        return _sorted_entries(entries)

    entries.append({
        "code": "BT",
        "summary_field": "tot_abnormal",
        "fraction": 1.0,
        "is_abnormal": True,
    })
    return entries


def _sorted_entries(entries):
    return sorted(entries, key=lambda e: STATUS_PRIORITY.get(e["code"], 99))
