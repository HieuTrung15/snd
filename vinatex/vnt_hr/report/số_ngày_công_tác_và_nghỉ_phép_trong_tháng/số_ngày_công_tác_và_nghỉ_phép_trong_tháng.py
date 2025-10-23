# -*- coding: utf-8 -*-
import json
from datetime import timedelta

import frappe
from frappe.utils import cint, get_first_day, get_last_day, getdate, today

BUSINESS_TRIP_TYPE = "Công tác"
APPROVED_TRIP_STATE = "Đã duyệt"

LEAVE_TYPES = {
    BUSINESS_TRIP_TYPE: {"code": "CT", "summary_field": "tot_business_trip"},
    "Nghỉ phép năm": {"code": "P", "summary_field": "tot_annual_leave"},
}

SUMMARY_COLUMNS = [
    {"fieldname": "tot_business_trip", "label": "Công tác", "fieldtype": "Float", "width": 90},
    {"fieldname": "tot_annual_leave", "label": "Nghỉ phép", "fieldtype": "Float", "width": 100},
    {"fieldname": "tot_total", "label": "Tổng", "fieldtype": "Float", "width": 80},
]

LEGEND_HTML = (
    "<div style='margin-top:8px;'>"
    "<strong>Chú thích:</strong> "
    "<span><strong>CT</strong>: Ngày đi công tác; </span>"
    "<span><strong>P</strong>: Nghỉ phép năm; </span>"
    # "<span><strong>P(0.5)</strong>: Nghỉ nửa ngày.</span>"
    "</div>"
)


def execute(filters=None):
    """
    Báo cáo số ngày Công tác + Nghỉ phép theo từng ngày trong khoảng tháng (mặc định tháng hiện tại).
    - Giữ cột đầu tiên `value` để số liệu vẫn dùng được cho Number Card như trước.
    - Bảng thể hiện từng ngày (CT, P, CT(0.5), ...), cộng dồn tổng theo loại.
    - Nếu không truyền employee, tự động map từ user đăng nhập.
    - Hỗ trợ filters:
        {"month": 9, "year": 2025}
        {"from_date": "2025-09-01", "to_date": "2025-09-30"}
        {"employee": "EMP-0001"}
        {"to_today": 0}  # Chỉ tính tới hôm nay
    """

    filters = _parse_filters(filters)

    employee = filters.get("employee") or _employee_from_session()
    if not employee:
        return _columns(), [{"value": 0.0}], None

    start_date, end_date = _resolve_period(filters)
    # if cint(filters.get("to_today") or 0):
    #     end_date = min(end_date, getdate(today()))
    if end_date < start_date:
        return _columns(), [{"value": 0.0}], None

    emp_doc = _get_employee_doc(employee)
    days = list(_daterange(start_date, end_date))
    leave_rows = _fetch_leaves(employee, start_date, end_date)
    trip_rows = _fetch_business_trips(employee, start_date, end_date)
    leave_map = _expand_leave_rows(leave_rows + trip_rows, start_date, end_date)

    columns = _columns() + _info_columns() + _day_columns(days) + SUMMARY_COLUMNS

    totals = {col["fieldname"]: 0.0 for col in SUMMARY_COLUMNS}
    row = {
        "employee": employee,
        "employee_name": emp_doc.get("employee_name") if emp_doc else employee,
        "department": emp_doc.get("department") if emp_doc else None,
        "company": emp_doc.get("company") if emp_doc else None,
    }

    total_value = 0.0
    for day in days:
        fieldname = f"d{day.day:02d}"
        entries = leave_map.get(day, [])
        if not entries:
            row[fieldname] = ""
            continue

        parts = []
        daily_total = 0.0
        for entry in _sorted_entries(entries):
            code = entry["code"]
            fraction = entry["fraction"]
            label = code if fraction == 1 else f"{code}(0.5)"
            parts.append(label)

            summary_field = entry["summary_field"]
            if summary_field in totals:
                totals[summary_field] += fraction
            daily_total += fraction

        row[fieldname] = "/".join(parts)
        total_value += daily_total

    totals["tot_total"] = total_value
    for key, value in totals.items():
        row[key] = float(value)

    row["value"] = float(total_value)

    return columns, [row], LEGEND_HTML


def _columns():
    return [{
        "label": "Số ngày nghỉ (Công tác + Phép năm)",
        "fieldname": "value",
        "fieldtype": "Float",
        "width": 180,
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
            "width": 140,
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
            "width": 50,
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
    return start, end


def _get_employee_doc(employee):
    return frappe.db.get_value(
        "Employee",
        employee,
        ["employee_name", "department", "company"],
        as_dict=True,
    ) or {}


def _daterange(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _fetch_leaves(employee, start_date, end_date):
    leave_types = [lt for lt in LEAVE_TYPES if lt != BUSINESS_TRIP_TYPE]
    if not leave_types:
        return []
    if len(leave_types) == 1:
        leave_types = (leave_types[0], leave_types[0])
    else:
        leave_types = tuple(leave_types)
    return frappe.db.sql(
        """
        SELECT leave_type, from_date, to_date, half_day, half_day_date
        FROM `tabLeave Application`
        WHERE employee = %(employee)s
          AND docstatus = 1
          AND status = 'Approved'
          AND leave_type IN %(leave_types)s
          AND to_date   >= %(start)s
          AND from_date <= %(end)s
        """,
        {
            "employee": employee,
            "start": start_date,
            "end": end_date,
            "leave_types": leave_types,
        },
        as_dict=True,
    )


def _fetch_business_trips(employee, start_date, end_date):
    rows = frappe.db.sql(
        """
        SELECT DISTINCT p.name, p.from_date, p.to_date
        FROM `tabVNT Business Trip Request` p
        LEFT JOIN `tabVNT Business Trip Request Items` i ON i.parent = p.name
        WHERE p.workflow_state = %(approved)s
          AND (p.employee = %(employee)s OR i.employee = %(employee)s)
          AND NOT (p.to_date < %(start)s OR p.from_date > %(end)s)
        """,
        {
            "approved": APPROVED_TRIP_STATE,
            "employee": employee,
            "start": start_date,
            "end": end_date,
        },
        as_dict=True,
    )

    results = []
    for row in rows:
        from_date = getdate(row.from_date) if row.from_date else None
        to_date = getdate(row.to_date) if row.to_date else from_date
        if not from_date:
            continue
        if to_date and to_date < from_date:
            from_date, to_date = to_date, from_date
        results.append(frappe._dict({
            "leave_type": BUSINESS_TRIP_TYPE,
            "from_date": from_date,
            "to_date": to_date or from_date,
            "half_day": 0,
            "half_day_date": None,
        }))

    return results


def _expand_leave_rows(rows, start_date, end_date):
    """Trả map {date -> [ {code, fraction, summary_field}, ... ]}."""
    out = {}
    for row in rows:
        config = LEAVE_TYPES.get(row.leave_type)
        if not config:
            continue

        current = max(getdate(row.from_date), start_date)
        last = min(getdate(row.to_date), end_date)
        half_day_date = getdate(row.half_day_date) if row.half_day and row.half_day_date else None

        while current <= last:
            fraction = 0.5 if half_day_date and current == half_day_date else 1.0
            out.setdefault(current, []).append({
                "code": config["code"],
                "summary_field": config["summary_field"],
                "fraction": fraction,
            })
            current += timedelta(days=1)
    return out


def _sorted_entries(entries):
    priority = {cfg["code"]: idx for idx, cfg in enumerate(LEAVE_TYPES.values())}
    return sorted(entries, key=lambda e: priority.get(e["code"], 99))
