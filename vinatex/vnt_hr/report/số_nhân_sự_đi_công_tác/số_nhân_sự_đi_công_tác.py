# -*- coding: utf-8 -*-
import frappe
from frappe.utils import getdate, add_days, nowdate
from datetime import timedelta
from collections import defaultdict

# ---- Utilities ----
def _week_bounds(base=None):
    d = getdate(base or nowdate())
    start = d - timedelta(days=d.weekday())  # Monday
    end = start + timedelta(days=6)          # Sunday
    return start, end

def _resolve_dates(filters):
    """
    Ưu tiên:
    - nếu filters['week'] == 'this' | 'last' -> auto tuần
    - nếu from_date/to_date trống -> auto tuần hiện tại
    - ngược lại dùng from_date/to_date đã truyền
    """
    week = (filters.get("week") or "").strip().lower()
    base = nowdate()
    if week == "last":
        # lùi 7 ngày rồi tính tuần
        base = add_days(base, -7)

    ws, we = _week_bounds(base)
    fd = filters.get("from_date")
    td = filters.get("to_date")
    from_date = getdate(fd) if fd else ws
    to_date   = getdate(td) if td else we
    return from_date, to_date

# ---- Report ----
def execute(filters=None):
    filters = (filters or {}).copy()
    mode = (filters.get("mode") or "").strip().lower()  # "" | "nc"
    leave_type = (filters.get("type_leave") or "Công tác").strip() or "Công tác"
    department = filters.get("department")

    from_date, to_date = _resolve_dates(filters)

    # ====== NUMBER CARD MODE: trả về 1 hàng-1 cột ======
    if mode == "nc":
        # Đếm DISTINCT nhân sự trong khoảng ngày, gộp cả nhân viên chính và bảng con
        q_nc = """
            SELECT COUNT(DISTINCT emp_code) AS value
            FROM (
                -- nhân viên chính trên Leave Application
                SELECT la.employee AS emp_code
                FROM `tabLeave Application` la
                WHERE la.docstatus = 1
                  AND la.leave_type = %(leave_type)s
                  AND NOT (la.to_date < %(from_date)s OR la.from_date > %(to_date)s)
                {dept_main}

                UNION
                -- nhân viên trong bảng con Business Trip Items
                SELECT i.employee AS emp_code
                FROM `tabVNT Business Trip Request Items` i
                INNER JOIN `tabLeave Application` la2 ON la2.name = i.parent
                WHERE la2.docstatus = 1
                  AND la2.leave_type = %(leave_type)s
                  AND NOT (la2.to_date < %(from_date)s OR la2.from_date > %(to_date)s)
                {dept_child}
            ) u
        """.format(
            dept_main = "AND EXISTS (SELECT 1 FROM `tabEmployee` e WHERE e.name = la.employee AND e.department = %(department)s)" if department else "",
            dept_child = "AND EXISTS (SELECT 1 FROM `tabEmployee` e2 WHERE e2.name = i.employee AND e2.department = %(department)s)" if department else "",
        )
        val = frappe.db.sql(q_nc, {
            "leave_type": leave_type,
            "from_date": from_date,
            "to_date": to_date,
            "department": department,
        }, as_dict=True)[0]["value"] or 0

        columns = [{"label": "Value", "fieldname": "value", "fieldtype": "Int", "width": 120}]
        rows = [{"value": int(val)}]
        # Number Card kiểu Report KHÔNG đọc report_summary/chart, chỉ cần rows
        return columns, rows

    # ====== MODE CHI TIẾT (UI mở báo cáo) ======
    columns = [
        {"label": "Mã NV",       "fieldname": "employee",      "fieldtype": "Data", "options": "Employee",   "width": 120},
        {"label": "Tên NV",      "fieldname": "employee_name", "fieldtype": "Data",                             "width": 200},
        {"label": "Phòng ban",   "fieldname": "department",    "fieldtype": "Data", "options": "Department", "width": 300},
        {"label": "Từ ngày",     "fieldname": "from_date",     "fieldtype": "Date",                            "width": 100},
        {"label": "Đến ngày",    "fieldname": "to_date",       "fieldtype": "Date",                            "width": 100},
        {"label": "Số ngày",     "fieldname": "days",          "fieldtype": "Float",                           "width": 100},
        {"label": "Mã số phiếu", "fieldname": "leave_app",     "fieldtype": "Data", "options": "Leave Application", "width": 140},
        {"label": "Đếm",         "fieldname": "count",         "fieldtype": "Float", "width": 50, "hidden": 1}
    ]

    # Lấy nhân sự từ cả nhân viên chính của Leave Application và các dòng trong bảng con
    q = """
        SELECT *
        FROM (
            -- 1) Nhân viên chính trên Leave Application
            SELECT
                la.employee           AS employee,
                emp.employee_name     AS employee_name,
                emp.department        AS department,
                la.from_date          AS from_date,
                la.to_date            AS to_date,
                la.name               AS leave_app,
                1                     AS count
            FROM `tabLeave Application` la
            INNER JOIN `tabEmployee` emp ON emp.name = la.employee
            WHERE la.docstatus = 1
              AND la.leave_type = %(leave_type)s
              AND NOT (la.to_date < %(from_date)s OR la.from_date > %(to_date)s)
              {dept_clause_main}

            UNION ALL

            -- 2) Nhân viên ở bảng con Business Trip Items
            SELECT
                i.employee            AS employee,
                emp2.employee_name    AS employee_name,
                emp2.department       AS department,
                la2.from_date         AS from_date,
                la2.to_date           AS to_date,
                la2.name              AS leave_app,
                1                     AS count
            FROM `tabVNT Business Trip Request Items` i
            INNER JOIN `tabLeave Application` la2 ON la2.name = i.parent
            INNER JOIN `tabEmployee` emp2 ON emp2.name = i.employee
            WHERE la2.docstatus = 1
              AND la2.leave_type = %(leave_type)s
              AND NOT (la2.to_date < %(from_date)s OR la2.from_date > %(to_date)s)
              {dept_clause_child}
        ) u
        ORDER BY u.department, u.employee_name, u.from_date
    """.format(
        dept_clause_main  = "AND emp.department  = %(department)s" if department else "",
        dept_clause_child = "AND emp2.department = %(department)s" if department else "",
    )

    data = frappe.db.sql(q, {
        "leave_type": leave_type,
        "from_date": from_date,
        "to_date": to_date,
        "department": department
    }, as_dict=1)

    rows = []
    today = getdate(nowdate())
    on_trip_today = set()
    by_day_counts = defaultdict(set)  # date -> set(employee)

    for r in data:
        s = max(getdate(r.from_date), from_date)
        e = min(getdate(r.to_date), to_date)
        r["from_date"] = getdate(r.from_date)
        r["to_date"]   = getdate(r.to_date)
        r["days"]      = float((e - s).days + 1)
        rows.append(r)

        if s <= today <= e:
            on_trip_today.add(r["employee"])
        d = s
        while d <= e:
            by_day_counts[d].add(r["employee"])
            d += timedelta(days=1)

    # report_summary cho UI (Number Card không dùng phần này)
    report_summary = [
        {"label": "Tổng số nhân sự đi công tác", "value": len({x["employee"] for x in rows}), "indicator": "blue"},
        {"label": "Đang công tác (hôm nay)",     "value": len(on_trip_today),                   "indicator": "green" if on_trip_today else "gray"},
    ]
