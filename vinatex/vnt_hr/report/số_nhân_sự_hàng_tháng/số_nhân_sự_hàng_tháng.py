# -*- coding: utf-8 -*-
import calendar
from datetime import date
import frappe
from frappe import _

def execute(filters=None):
    f = normalize(filters or {})
    months = month_buckets(f["from_year"], f["from_month"], f["to_year"], f["to_month"])

    first_all = months[0][1]
    last_all  = months[-1][2]

    where, params = [], {}
    where.append("emp.date_of_joining <= %(last_all)s")
    where.append("(emp.relieving_date IS NULL OR emp.relieving_date >= %(first_all)s)")
    params.update({"first_all": first_all, "last_all": last_all})

    if f["company"]:
        where.append("emp.company = %(company)s")
        params["company"] = f["company"]

    if f["department"]:
        where.append("emp.department = %(department)s")
        params["department"] = f["department"]

    sql = f"""
        SELECT emp.name, emp.date_of_joining, emp.relieving_date
        FROM `tabEmployee` emp
        WHERE {' AND '.join(where)}
    """
    employees = frappe.db.sql(sql, params, as_dict=True)

    # Đếm nhân sự từng tháng
    rows = []
    for ym, first_day, last_day in months:
        c = sum(
            1 for e in employees
            if e["date_of_joining"] <= last_day and (not e["relieving_date"] or e["relieving_date"] >= first_day)
        )
        rows.append({"month": ym, "headcount": c})

    # Tính bình quân năm
    avg = round(sum(r["headcount"] for r in rows) / len(rows), 1) if rows else 0
    for r in rows:
        r["avg_headcount"] = avg

    return get_columns(), rows, None, get_chart(rows, avg)


# ---------------- helpers ----------------

def normalize(f):
    today = date.today()
    fy = cint(f.get("from_year") or today.year)
    ty = cint(f.get("to_year") or fy)
    fm = cint(f.get("from_month") or 1)
    tm = cint(f.get("to_month") or 12)
    if (ty, tm) < (fy, fm):
        ty, tm = fy, fm
    return {
        "company": f.get("company"),
        "department": f.get("department"),
        "from_year": fy, "from_month": fm,
        "to_year": ty, "to_month": tm,
    }

def cint(x):
    try: return int(x)
    except: return 0

def month_buckets(fy, fm, ty, tm):
    buckets = []
    y, m = fy, fm
    while (y < ty) or (y == ty and m <= tm):
        first = date(y, m, 1)
        last  = date(y, m, calendar.monthrange(y, m)[1])
        buckets.append((f"{y}-{m:02d}", first, last))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return buckets

def get_columns():
    return [
        {"label": _("Tháng"), "fieldname": "month", "fieldtype": "Data", "width": 110},
        {"label": _("Số nhân sự (Headcount)"), "fieldname": "headcount", "fieldtype": "Int", "width": 160},
        {"label": _("Lao động bình quân năm"), "fieldname": "avg_headcount", "fieldtype": "Float", "width": 180, "hidden":1},
    ]

def get_chart(rows, avg):
    labels = [r["month"] for r in rows]
    values = [r["headcount"] for r in rows]
    avg_values = [avg] * len(rows)

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "name": _("Số nhân sự"),
                    "values": values,
                    "chartType": "bar",
                    "color": "#3288f1",   # xanh dương
                },
                {
                    "name": _("Bình quân năm"),
                    "values": avg_values,
                    "chartType": "bar",
                    "color": "#f5a623",   # cam
                },
            ],
        },
        "type": "bar",
        "height": 280,
        "colors": ["#3288f1", "#f5a623"],
        "axisOptions": {
            "xAxisMode": "tick",
            "yAxisMode": "tick",
            "xIsSeries": 1,
        },
        "barOptions": {
            "spaceRatio": 0.3
        },
    }
