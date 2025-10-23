# -*- coding: utf-8 -*-
import json
from datetime import datetime, timedelta, time

import frappe
from frappe.utils import cint, get_datetime, get_first_day, get_last_day, getdate, today,add_days

SUMMARY_COLUMNS = [
    # {"fieldname": "tot_abnormal", "label": "Ngày bất thường", "fieldtype": "Float", "width": 130},
    # {"fieldname": "tot_present", "label": "Có Attendance", "fieldtype": "Int", "width": 120},
    # {"fieldname": "tot_leave_full", "label": "Nghỉ (cả ngày)", "fieldtype": "Int", "width": 100},
    # {"fieldname": "tot_leave_half", "label": "Nghỉ (nửa ngày)", "fieldtype": "Float", "width": 110},
    # {"fieldname": "tot_holiday", "label": "Holiday", "fieldtype": "Int", "width": 90},
    # {"fieldname": "tot_not_joined", "label": "Chưa vào làm", "fieldtype": "Int", "width": 120},
]

STATUS_PRIORITY = {
    "CV": 0,
    "L": 1,
    "X": 2,
    "P": 3,
    "P(0.5)": 4,
    "T": 5,
    "BT": 6,
    "BT(0.5)": 7,
}
# Cấu hình giờ vào ra
STANDARD_START_TIME = time(8, 15)
STANDARD_END_TIME = time(17, 0)
LEGEND_HTML = (
    "<div style='margin-top:8px;'>"
    "<strong>Chú thích:</strong> "
    "<span><strong>BT</strong>: Bất thường (đi muộn, về sớm hoặc không có chấm công). </span>"
    "</div>"
)


def execute(filters=None):
    """
    Báo cáo số ngày chấm công bất thường (chỉ tính cho 1 nhân viên).
    - Giữ cột đầu tiên 'value' để Number Card có thể đọc được tổng ngày bất thường.
    - Bảng hiển thị từng ngày với các mã:
        * BT / BT(0.5): ngày bất thường (full hoặc nửa ngày)
        * X: có Attendance
        * P / P(0.5): nghỉ phép full / nửa ngày
        * L: Holiday
        * CV: trước ngày vào làm
    - Half-day leave -> hiển thị P(0.5)/BT(0.5) và cộng 0.5 ngày bất thường.
    """

    filters = _parse_filters(filters)

    employee = filters.get("employee") or _employee_from_session()
    if not employee:
        return _columns(), [{"value": 0.0}], None

    start_date, end_date = _resolve_period(filters)
    if cint(filters.get("to_today") or 0):
        end_date = min(end_date, getdate(add_days(today(),-1)))
    if end_date < start_date:
        return _columns(), [{"value": 0.0}], None

    emp_doc = _get_employee_doc(employee)
    days = list(_daterange(start_date, end_date))

    holiday_days, weekend_days = _holiday_days(emp_doc, start_date, end_date)
    attendance_map = _attendance_map(employee, start_date, end_date)
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
        entries = _classify_day(day, emp_doc, holiday_days, weekend_days, attendance_map, leave_map)
        fieldname = f"d{day.day:02d}"
        if not entries:
            row[fieldname] = ""
            continue

        labels = []
        display_labels = []
        for entry in entries:
            labels.append(entry["code"])
            fraction = entry.get("fraction", 1.0)
            summary_fields = entry.get("summary_fields") or []
            if not summary_fields and entry.get("summary_field"):
                summary_fields = [entry["summary_field"]]
            for summary_field in summary_fields:
                if summary_field in totals:
                    totals[summary_field] += fraction
            if entry.get("is_abnormal"):
                total_abnormal += fraction
            if entry["code"].startswith("BT"):
                display_labels.append(entry["code"])

        row[fieldname] = "/".join(display_labels) if display_labels else ""

    for key, value in totals.items():
        if key in {"tot_present", "tot_holiday", "tot_leave_full", "tot_not_joined"}:
            row[key] = int(value)
        else:
            row[key] = float(value)

    row["value"] = float(total_abnormal)

    return columns, [row], LEGEND_HTML


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

    ref_date = getdate(add_days(today(),-1))
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


def _attendance_map(employee, start_date, end_date):
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

    out = {}
    for r in rows:
        day = getdate(r.attendance_date)
        out[day] = {
            "has_attendance": True,
            "in_time": None,
            "out_time": None,
        }

    checkins = frappe.db.sql(
        """
        SELECT DATE(time) AS checkin_date,
               MIN(CASE WHEN UPPER(TRIM(log_type)) = 'IN'  THEN time END) AS in_time,
               MAX(CASE WHEN UPPER(TRIM(log_type)) = 'OUT' THEN time END) AS out_time
        FROM `tabEmployee Checkin`
        WHERE employee = %(employee)s
          AND DATE(time) BETWEEN %(start)s AND %(end)s
          AND UPPER(TRIM(log_type)) IN ('IN', 'OUT')
        GROUP BY DATE(time)
    """,
        {"employee": employee, "start": start_date, "end": end_date},
        as_dict=True,
    )

    for row in checkins:
        day = getdate(row.checkin_date)
        entry = out.setdefault(day, {
            "has_attendance": False,
            "in_time": None,
            "out_time": None,
        })
        entry["in_time"] = row.in_time
        entry["out_time"] = row.out_time

    return out


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


def _classify_day(day, emp_doc, holiday_days, weekend_days, attendance_map, leave_map):
    entries = []
    doj = emp_doc.get("date_of_joining")
    doj = getdate(doj) if doj else None

    # if doj and day < doj:
    #     entries.append({
    #         "code": "CV",
    #         "summary_field": "tot_not_joined",
    #         "fraction": 1.0,
    #     })
    #     return entries

    if day in holiday_days:
        entries.append({
            "code": "L",
            "summary_field": "tot_holiday",
            "fraction": 1.0,
        })
        return entries

    if day in weekend_days:
        entries.append({
            "code": "T",
            "fraction": 0.0,
        })
        return entries

    attendance = attendance_map.get(day)
    if attendance:
        if attendance.get("has_attendance"):
            if _is_abnormal_attendance(attendance):
                entries.append({
                    "code": "BT",
                    "summary_fields": ["tot_abnormal", "tot_present"],
                    "fraction": 1.0,
                    "is_abnormal": True,
                })
            else:
                entries.append({
                    "code": "X",
                    "summary_fields": ["tot_present"],
                    "fraction": 1.0,
                })
            return entries

        if attendance.get("in_time") or attendance.get("out_time"):
            if _is_abnormal_attendance(attendance):
                entries.append({
                    "code": "BT",
                    "summary_fields": ["tot_abnormal"],
                    "fraction": 1.0,
                    "is_abnormal": True,
                })
            else:
                entries.append({
                    "code": "X",
                    "fraction": 1.0,
            })
            return entries

    leave = leave_map.get(day)
    if leave:
        fraction = leave["fraction"]
        if fraction >= 1:
            entries.append({
                "code": "P",
                "summary_field": "tot_leave_full",
                "fraction": 1.0,
            })
            return entries

        # half-day leave + 0.5 abnormal
        entries.append({
            "code": "P(0.5)",
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


def _is_abnormal_attendance(attendance):
    in_time = _as_time(attendance.get("in_time"))
    out_time = _as_time(attendance.get("out_time"))

    if in_time is None or out_time is None:
        return True
    if in_time and in_time > STANDARD_START_TIME:
        return True
    if out_time and out_time < STANDARD_END_TIME:
        return True
    return False


def _as_time(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        return get_datetime(value).time()
    return value
