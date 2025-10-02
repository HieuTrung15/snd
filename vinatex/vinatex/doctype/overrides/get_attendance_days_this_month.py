# Copyright (c) 2025
import frappe
from frappe.utils import get_first_day, get_last_day, today, cint

@frappe.whitelist()
def get_attendance_days_this_month(filters=None):
    import json
    from frappe.utils import get_first_day, get_last_day, today, getdate, cint

    if isinstance(filters, str):
        try:
            filters = frappe.parse_json(filters)
        except Exception:
            try:
                filters = json.loads(filters)
            except Exception:
                filters = None
    filters = filters or {}

    # Map user -> employee
    employee = filters.get("employee") or frappe.db.get_value(
        "Employee",
        {"user_id": frappe.session.user, "status": "Active"},
        "name",
    )
    if not employee:
        return 0.0

    # Xác định khoảng tháng
    ref_date = getdate(today())
    month = cint(filters.get("month") or 0)
    year  = cint(filters.get("year") or 0)

    if month and year:
        start_date = get_first_day(getdate(f"{year:04d}-{month:02d}-01"))
    else:
        start_date = get_first_day(ref_date)
        year = start_date.year
        month = start_date.month

    end_date = get_last_day(start_date)

    # Tùy chọn: tính WFH như Present
    count_wfh = cint(filters.get("count_wfh") or 0)
    wfh_cond = " OR a.status = 'Work From Home'" if count_wfh else ""

    # Tính tổng ngày công
    sql = f"""
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN (a.status = 'Present' {wfh_cond}) THEN 1
                    WHEN a.status = 'Half Day' THEN 0.5
                    ELSE 0
                END
            ), 0) AS days
        FROM `tabAttendance` a
        WHERE a.employee = %(employee)s
          AND a.attendance_date BETWEEN %(from)s AND %(to)s
          AND a.docstatus = 1
    """
    res = frappe.db.sql(sql, {"employee": employee, "from": start_date, "to": end_date}, as_dict=True)
    return float(res[0].days or 0.0)

