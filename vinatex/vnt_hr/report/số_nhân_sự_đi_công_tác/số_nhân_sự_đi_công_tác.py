# -*- coding: utf-8 -*-
# Report: Số nhân sự đi công tác (Tuần - Auto) — KHÔNG dùng dòng giả, KHÔNG STT
import frappe
from frappe.utils import getdate, nowdate
from datetime import timedelta

APPROVED = "Đã duyệt"

def _week_bounds(base=None):
    d = getdate(base or nowdate())
    start = d - timedelta(days=d.weekday())   # Monday
    end = start + timedelta(days=6)           # Sunday
    return start, end

@frappe.whitelist()
def execute(filters=None):
    week_start, week_end = _week_bounds()
    today = getdate(nowdate())

    sql = """
        SELECT DISTINCT
            u.emp_code,
            e.employee_name,
            e.department,
            e.branch,
            u.destination,
            u.from_date,
            u.to_date
        FROM (
            -- A. Nhân viên ở bảng con (nhiều người đi cùng)
            SELECT
                i.employee AS emp_code,
                p.destination,
                p.from_date,
                p.to_date
            FROM `tabVNT Business Trip Request` p
            INNER JOIN `tabVNT Business Trip Request Items` i ON i.parent = p.name
            WHERE p.workflow_state = %(approved)s
              AND NOT (p.to_date < %(from)s OR p.from_date > %(to)s)

            UNION ALL

            -- B. Nhân viên chính ở phiếu (employee là bắt buộc)
            SELECT
                p.employee AS emp_code,
                p.destination,
                p.from_date,
                p.to_date
            FROM `tabVNT Business Trip Request` p
            WHERE p.workflow_state = %(approved)s
              AND NOT (p.to_date < %(from)s OR p.from_date > %(to)s)
        ) u
        INNER JOIN `tabEmployee` e ON e.name = u.emp_code
    """
    params = {"approved": APPROVED, "from": week_start, "to": week_end}
    rows = frappe.db.sql(sql, params, as_dict=True)

    # Chuẩn hoá và cắt theo tuần
    for r in rows:
        r["from_date"] = max(getdate(r["from_date"]), week_start)
        r["to_date"]   = min(getdate(r["to_date"]), week_end)
        r["destination"] = r.get("destination") or ""

    # Tổng unique theo mã NV (chỉ dữ liệu thật)
    unique_employees = {r["emp_code"] for r in rows}
    total_in_week = len(unique_employees)

    # Đang công tác hôm nay
    employees_today = {
        r["emp_code"]
        for r in rows
        if r["from_date"] <= today <= r["to_date"]
    }

    # Sắp xếp tăng dần theo ngày, rồi tên
    rows.sort(key=lambda x: (x["from_date"], x.get("employee_name") or ""))

    # Gán tổng (để Number Card đọc khi có dữ liệu)
    for r in rows:
        r["total_in_week"] = total_in_week

    # Summary (rỗng thì tự = 0)
    report_summary = [
        {"label": "Tuần", "value": f"{week_start.strftime('%d-%m-%Y')} → {week_end.strftime('%d-%m-%Y')}", "indicator": "blue"},
        {"label": "Tổng nhân sự đi công tác (unique)", "value": total_in_week, "indicator": "green" if total_in_week else "gray"},
        {"label": "Đang công tác hôm nay", "value": len(employees_today), "indicator": "green" if employees_today else "gray"},
    ]

    columns = [
        {"label": "Số nhân sự đi công tác trong tuần", "fieldname": "total_in_week", "fieldtype": "Int", "width": 220, "hidden":1},
        {"label": "Mã NV", "fieldname": "emp_code", "fieldtype": "Link", "options": "Employee", "width": 120},
        {"label": "Tên NV", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "Phòng ban", "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 200},
        {"label": "Chi nhánh", "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 200},
        {"label": "Địa điểm công tác", "fieldname": "destination", "fieldtype": "Data", "width": 200},
        {"label": "Từ ngày", "fieldname": "from_date", "fieldtype": "Date", "width": 110},
        {"label": "Đến ngày", "fieldname": "to_date", "fieldtype": "Date", "width": 110},
    ]

    return columns, rows, None, None, report_summary
