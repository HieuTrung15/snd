import frappe
from frappe.utils import getdate, add_days, nowdate
from datetime import date, timedelta
from collections import defaultdict

def _week_bounds(d=None):
    d = getdate(d or nowdate())
    # ERPNext: Monday=0, Sunday=6
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    return start, end

def execute(filters=None):
    filters = filters or {}
    # defaults
    if not filters.get("from_date") or not filters.get("to_date"):
        ws, we = _week_bounds(filters.get("target_date"))
        filters["from_date"] = filters.get("from_date") or ws
        filters["to_date"]   = filters.get("to_date")   or we

    leave_type = "Công tác"
    department = filters.get("department")
    from_date = getdate(filters["from_date"])
    to_date   = getdate(filters["to_date"])

    columns = [
        {"label": "Mã NV", "fieldname": "employee", "fieldtype": "Data", "options": "Employee", "width": 120},
        {"label": "Tên NV", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "Phòng ban", "fieldname": "department", "fieldtype": "Data", "options": "Department", "width": 350},
        {"label": "Từ ngày", "fieldname": "from_date", "fieldtype": "Date", "width": 100},
        {"label": "Đến ngày", "fieldname": "to_date", "fieldtype": "Date", "width": 100},
        {"label": "Số ngày", "fieldname": "days", "fieldtype": "Float", "width": 110},
        {"label": "Đơn xin nghỉ", "fieldname": "leave_app", "fieldtype": "Data", "options": "Leave Application", "width": 140},
        {"label": "Đếm", "fieldname": "count", "fieldtype": "Float", "width": 50, "hidden": 1}
    ]

        # Lấy nhân sự từ cả nhân viên chính của Leave Application và các dòng trong bảng con
    q = """
        SELECT *
        FROM (
            -- 1) Nhân viên chính trên Leave Application
            SELECT
                la.employee                           AS employee,
                emp.employee_name                     AS employee_name,
                emp.department                        AS department,
                la.from_date                          AS from_date,
                la.to_date                            AS to_date,
                la.name                               AS leave_app,
                1                                     AS count
            FROM `tabLeave Application` la
            INNER JOIN `tabEmployee` emp ON emp.name = la.employee
            WHERE la.docstatus = 1
              AND (%(leave_type)s IS NULL OR la.leave_type = %(leave_type)s)
              AND NOT (la.to_date < %(from_date)s OR la.from_date > %(to_date)s)
              {dept_clause_main}

            UNION ALL

            -- 2) Nhân viên ở bảng con Business Trip Items
            SELECT
                i.employee                            AS employee,
                emp2.employee_name                    AS employee_name,
                emp2.department                       AS department,
                la2.from_date                         AS from_date,
                la2.to_date                           AS to_date,
                la2.name                              AS leave_app,
                1                                     AS count
            FROM `tabVNT Business Trip Request Items` i
            INNER JOIN `tabLeave Application` la2 ON la2.name = i.parent
            INNER JOIN `tabEmployee` emp2 ON emp2.name = i.employee
            WHERE la2.docstatus = 1
              AND (%(leave_type)s IS NULL OR la2.leave_type = %(leave_type)s)
              AND NOT (la2.to_date < %(from_date)s OR la2.from_date > %(to_date)s)
              {dept_clause_child}
        ) u
        ORDER BY u.department, u.employee_name, u.from_date
    """.format(
        # Lọc theo phòng ban dựa trên Department của Employee (nhất quán cho cả 2 nhánh)
        dept_clause_main = "AND emp.department = %(department)s" if department else "",
        dept_clause_child = "AND emp2.department = %(department)s" if department else "",
    )


    rows = []
    unique_people = set()
    today = getdate(nowdate())
    on_trip_today = set()

    data = frappe.db.sql(q, {
        "leave_type": leave_type,
        "from_date": from_date,
        "to_date": to_date,
        "department": department
    }, as_dict=1)

    # dùng để build chart (đếm người theo ngày)
    by_day_counts = defaultdict(set)  # date -> set(employee)

    for r in data:
        s = max(getdate(r.from_date), from_date)
        e = min(getdate(r.to_date), to_date)
        days = (e - s).days + 1
        r["from_date"] = getdate(r.from_date)
        r["to_date"] = getdate(r.to_date)
        r["days"] = float(days)
        rows.append(r)
        unique_people.add((r["employee"], r["leave_app"]))
        if s <= today <= e:
            on_trip_today.add(r["employee"])

        d = s
        while d <= e:
            by_day_counts[d].add(r["employee"])
            d += timedelta(days=1)

    # report_summary
    report_summary = [
        {
            "label": "Tổng số nhân sự đi công tác",
            "value": len({emp for emp, _ in unique_people}) if rows else 0,
            "indicator": "blue"
        },
        {
            "label": "Đang công tác (hôm nay)",
            "value": len(on_trip_today) if rows else 0,
            "indicator": "green" if on_trip_today else "gray"
        }
    ]

    # === CHART: tự động gom nhóm theo span (ngày/tuần/tháng) ===
    def iter_days(s, e):
        d = s
        while d <= e:
            yield d
            d += timedelta(days=1)

    span_days = (to_date - from_date).days + 1
    labels, values = [], []

    if span_days <= 31:
        # Theo ngày
        for day in iter_days(from_date, to_date):
            labels.append(day.strftime("%d-%m"))
            values.append(len(by_day_counts.get(day, set())) if rows else 0)
        chart_type = "bar"
    elif span_days <= 180:
        # Theo tuần (T2–CN), lấy max trong tuần
        cur = from_date
        while cur <= to_date:
            week_start = cur - timedelta(days=cur.weekday())
            if week_start < from_date:
                week_start = from_date
            week_end = min(week_start + timedelta(days=6), to_date)

            week_vals = []
            d = week_start
            while d <= week_end:
                week_vals.append(len(by_day_counts.get(d, set())) if rows else 0)
                d += timedelta(days=1)

            labels.append(f"Tuần {week_start.strftime('%d-%m')}→{week_end.strftime('%d-%m')}")
            values.append(max(week_vals) if week_vals else 0)

            cur = week_end + timedelta(days=1)
        chart_type = "line"
    else:
        # Theo tháng, lấy max trong tháng
        cur = from_date.replace(day=1)
        while cur <= to_date:
            month_start = cur
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            month_start = max(month_start, from_date)
            month_end = min(month_end, to_date)

            month_vals = []
            d = month_start
            while d <= month_end:
                month_vals.append(len(by_day_counts.get(d, set())) if rows else 0)
                d += timedelta(days=1)

            labels.append(month_start.strftime("%m-%Y"))
            values.append(max(month_vals) if month_vals else 0)

            cur = (month_end + timedelta(days=1)).replace(day=1)
        chart_type = "line"

    chart = {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Số người công tác", "values": values}
            ]
        },
        "type": chart_type,
        "height": 220
    }

    # message nhẹ nhàng
    message = None
    if not rows:
        rows.append({
            "employee": "",
            "employee_name": "",
            "department": "",
            "from_date": from_date,
            "to_date": to_date,
            "days": 0.0,
            "leave_app": ""
        })

    return columns, rows, message, chart, report_summary
