# -*- coding: utf-8 -*-
# Report: Số nhân sự công tác (Tuần - Auto, có Địa điểm + Summary + Tổng nhân sự trong tuần + Sắp xếp theo ngày)
import frappe
from frappe.utils import getdate, nowdate
from datetime import timedelta
from collections import defaultdict

APPROVED = "Đã duyệt"

def _week_bounds(base=None):
    """Trả về (Thứ 2, Chủ nhật) của tuần hiện tại"""
    d = getdate(base or nowdate())
    start = d - timedelta(days=d.weekday())   # Monday
    end = start + timedelta(days=6)           # Sunday
    return start, end


def execute(filters=None):
    # Không dùng filters, luôn tính theo tuần hiện tại
    week_start, week_end = _week_bounds()

    # Lấy danh sách công tác đã duyệt, giao với tuần hiện tại
    sql = """
        SELECT DISTINCT
            u.emp_code,
            e.employee_name,
            e.department,
            u.destination,
            u.from_date,
            u.to_date
        FROM (
            -- Child items
            SELECT 
                i.employee AS emp_code, 
                p.destination,
                p.from_date, 
                p.to_date
            FROM `tabVNT Business Trip Request` p
            LEFT JOIN `tabVNT Business Trip Request Items` i ON i.parent = p.name
            WHERE p.workflow_state = %(approved)s
              AND i.employee IS NOT NULL
              AND NOT (p.to_date < %(from)s OR p.from_date > %(to)s)

            UNION ALL

            -- Parent requests
            SELECT 
                p.employee AS emp_code,
                p.destination,
                p.from_date,
                p.to_date
            FROM `tabVNT Business Trip Request` p
            WHERE p.workflow_state = %(approved)s
              AND p.employee IS NOT NULL
              AND NOT (p.to_date < %(from)s OR p.from_date > %(to)s)
        ) u
        INNER JOIN `tabEmployee` e ON e.name = u.emp_code
    """

    params = {"approved": APPROVED, "from": week_start, "to": week_end}
    rows = frappe.db.sql(sql, params, as_dict=True)

    # Gom nhân sự theo ngày trong tuần để tính tổng và số đang đi hôm nay
    by_day = defaultdict(set)
    today = getdate(nowdate())
    on_today = set()

    for r in rows:
        s = max(getdate(r["from_date"]), week_start)
        e = min(getdate(r["to_date"]), week_end)
        r["from_date"] = s
        r["to_date"] = e
        r["destination"] = r.get("destination") or ""

        # Đếm nhân sự theo ngày
        d = s
        while d <= e:
            by_day[d].add(r["emp_code"])
            d += timedelta(days=1)

        if s <= today <= e:
            on_today.add(r["emp_code"])

    # Tổng unique nhân sự trong tuần
    total_in_week = len(set().union(*by_day.values())) if by_day else 0

    # Gán số tổng này vào từng dòng dữ liệu
    for r in rows:
        r["total_in_week"] = total_in_week

    # Sắp xếp theo ngày đi công tác tăng dần, sau đó theo tên NV
    rows.sort(key=lambda x: (x["from_date"], x["employee_name"]))

    # ======= SUMMARY =======
    report_summary = [
        {"label": "Tuần", "value": f"{week_start.strftime('%d-%m-%Y')} → {week_end.strftime('%d-%m-%Y')}", "indicator": "blue"},
        {"label": "Tổng nhân sự đi công tác", "value": f"{total_in_week}  nhân sự", "indicator": "green" if total_in_week else "gray"},
        {"label": "Đang công tác hôm nay", "value": f"{len(on_today)} nhân sự", "indicator": "green" if on_today else "gray"},
    ]

    # ======= COLUMNS =======
    columns = [
        {"label": "Mã NV", "fieldname": "emp_code", "fieldtype": "Link", "options": "Employee", "width": 120},
        {"label": "Tên NV", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "Phòng ban", "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 220},
        {"label": "Địa điểm công tác", "fieldname": "destination", "fieldtype": "Data", "width": 200},
        {"label": "Từ ngày", "fieldname": "from_date", "fieldtype": "Date", "width": 110},
        {"label": "Đến ngày", "fieldname": "to_date", "fieldtype": "Date", "width": 110},
        {"label": "Tổng số NS trong tuần", "fieldname": "total_in_week", "fieldtype": "Int", "width": 180, "hidden":1}
    ]

    return columns, rows, None, None, report_summary
