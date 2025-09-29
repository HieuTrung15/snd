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

    # lấy các đơn công tác giao với [from_date, to_date]
    q = """
        SELECT
            i.employee, i.employee_name, i.department,
            t.from_date, t.to_date,
            i.parent as leave_app,
            1 as count
        FROM `tabVNT Business Trip Request Items` i
        INNER JOIN `tabVNT Leave Application Time` t ON t.parent = i.parent
        INNER JOIN `tabLeave Application` la ON la.name = i.parent
        WHERE la.docstatus = 1
          AND (%(leave_type)s IS NULL OR la.leave_type = %(leave_type)s)
          AND NOT (t.to_date < %(from_date)s OR t.from_date > %(to_date)s)
          {dept_clause}
        ORDER BY i.department, i.employee_name, t.from_date
    """.format(
        dept_clause = "AND i.department = %(department)s" if department else ""
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

    # report_summary: luôn có số liệu (0 nếu không có dữ liệu)
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

    # chart: luôn build, nếu không có dữ liệu thì values toàn 0
    labels, values = [], []
    day = from_date
    while day <= to_date:
        labels.append(day.strftime("%d-%m"))
        values.append(len(by_day_counts.get(day, set())) if rows else 0)
        day += timedelta(days=1)

    chart = {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Số người công tác", "values": values}
            ]
        },
        "type": "bar",
        "height": 200
    }

    # message hiển thị nhẹ nhàng (không bắt buộc)
    message = None
    if not rows:
        message = "Không có dữ liệu trong khoảng ngày đã chọn (đang hiển thị 0)."

        # ⚠️ quan trọng: thêm 1 hàng placeholder để tránh banner “Report has no data…”
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
