import frappe
from frappe.utils import getdate, nowdate, add_months, get_first_day, get_last_day

# key nội bộ để gom & sort (YYYY-MM)
def _month_key(d): 
    return d.strftime("%Y-%m")

# nhãn hiển thị cho người dùng (MM-YYYY)
def _label_from_key(k: str) -> str:
    y, m = k.split("-")
    return f"{m}-{y}"          # đổi thành f"{m}/{y}" nếu bạn muốn MM/YYYY

def _month_keys(start_date, end_date):
    keys, cur = [], get_first_day(start_date)
    end = get_first_day(end_date)
    while cur <= end:
        keys.append(_month_key(cur))
        cur = add_months(cur, 1)
    return keys

def _normalize_period(filters):
    to_date = getdate(filters.get("to_date") or nowdate())
    from_date = getdate(filters.get("from_date") or add_months(to_date, -11))
    return get_first_day(from_date), get_last_day(to_date)

def execute(filters=None):
    filters = frappe._dict(filters or {})
    from_date, to_date = _normalize_period(filters)
    company = filters.get("company")
    department = filters.get("department")

    where_join = ["date_of_joining BETWEEN %s AND %s"]
    where_left = ["relieving_date BETWEEN %s AND %s"]
    params_join = [from_date, to_date]
    params_left = [from_date, to_date]

    if company:
        where_join.append("company = %s");   params_join.append(company)
        where_left.append("company = %s");   params_left.append(company)
    if department:
        where_join.append("department = %s"); params_join.append(department)
        where_left.append("department = %s"); params_left.append(department)

    # Dùng YYYY-MM làm key nhóm trong SQL (ổn định cho ORDER/GROUP)
    hiring_rows = frappe.db.sql(
        f"""
        SELECT DATE_FORMAT(date_of_joining, '%%Y-%%m') AS ym_key, COUNT(*) AS c
        FROM `tabEmployee`
        WHERE {" AND ".join(where_join)}
        GROUP BY ym_key
        """,
        params_join, as_dict=True
    )
    attr_rows = frappe.db.sql(
        f"""
        SELECT DATE_FORMAT(relieving_date, '%%Y-%%m') AS ym_key, COUNT(*) AS c
        FROM `tabEmployee`
        WHERE relieving_date IS NOT NULL
          AND {" AND ".join(where_left)}
        GROUP BY ym_key
        """,
        params_left, as_dict=True
    )

    hire_map = {r.ym_key: int(r.c) for r in hiring_rows}
    attr_map = {r.ym_key: int(r.c) for r in attr_rows}

    months_keys = _month_keys(from_date, to_date)          # ['2025-01', ...]
    months_labels = [_label_from_key(k) for k in months_keys]  # ['01-2025', ...]

    data = [{
        "month": _label_from_key(k),
        "hiring_count": hire_map.get(k, 0),
        "attrition_count": attr_map.get(k, 0),
    } for k in months_keys]

    total_hire = sum(d["hiring_count"] for d in data)
    total_attr = sum(d["attrition_count"] for d in data)
    net = total_hire - total_attr

    columns = [
        {"label": "Tháng", "fieldname": "month", "fieldtype": "Data", "width": 120},
        {"label": "Tuyển dụng", "fieldname": "hiring_count", "fieldtype": "Int", "width": 120},
        {"label": "Nghỉ việc", "fieldname": "attrition_count", "fieldtype": "Int", "width": 120},
    ]

    chart = {
    "type": "line",
    "data": {
        "labels": months_labels,  # đang là MM-YYYY
        "datasets": [
            {"name": "Tuyển dụng", "values": [hire_map.get(k, 0) for k in months_keys]},
            {"name": "Nghỉ việc",  "values": [attr_map.get(k, 0) for k in months_keys]},
        ],
    },
    # màu giống screenshot: xanh nhạt & xanh dương
    "colors": ["#7cd6fd", "#5e64ff"],
    # bật fill dưới đường, hiện chấm
    "lineOptions": {"regionFill": 1, "hideDots": 0, "dotSize": 3},
    # không dùng timeseries vì label là MM-YYYY
    "timeseries": 0,
    "axisOptions": {"xAxisMode": "tick", "yAxisMode": "span", "xIsSeries": 0},
}

    report_summary = [
        {"label": "Tuyển dụng", "value": total_hire, "indicator": "blue"},
        {"label": "Nghỉ việc", "value": total_attr, "indicator": "red"},
        {"label": "Chênh lệch", "value": net, "indicator": "green" if net >= 0 else "red"},
    ]

    return columns, data, None, chart, report_summary, True
