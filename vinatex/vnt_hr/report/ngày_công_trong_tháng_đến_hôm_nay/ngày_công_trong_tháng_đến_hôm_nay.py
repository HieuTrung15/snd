# -*- coding: utf-8 -*-
import json
import frappe
from frappe.utils import get_first_day, get_last_day, today, getdate, cint

def execute(filters=None):
    """
    Trả về tổng NGÀY CÔNG trong tháng (đến HÔM NAY):
      - Present = 1
      - Half Day = 0.5
      - Work From Home = 1 (nếu bật count_wfh)
    Ưu tiên dùng from_date/to_date nếu truyền vào; end_date luôn cắt <= hôm nay.
    Nếu không truyền employee, tự map từ frappe.session.user -> Employee(Active).
    """

    # Parse filters an toàn
    if isinstance(filters, str):
        try:
            filters = frappe.parse_json(filters)
        except Exception:
            try:
                filters = json.loads(filters)
            except Exception:
                filters = {}
    filters = filters or {}

    # Map user -> employee (dùng RAW SQL để không dính ignore_permissions)
    employee = filters.get("employee")
    if not employee:
        row = frappe.db.sql(
            """SELECT name FROM `tabEmployee`
               WHERE user_id=%s AND status='Active' LIMIT 1""",
            (frappe.session.user,),
        )
        employee = row[0][0] if row else None
    if not employee:
        return _columns(), [{"value": 0.0}], None

    # Khoảng tính: ưu tiên from_date/to_date; luôn cắt end_date đến HÔM NAY
    ref_date = getdate(today())
    if filters.get("from_date"):
        start_date = getdate(filters["from_date"])
        end_date = getdate(filters.get("to_date") or ref_date)
    else:
        month = cint(filters.get("month") or 0)
        year  = cint(filters.get("year")  or 0)
        if month and year:
            start_date = get_first_day(getdate(f"{year:04d}-{month:02d}-01"))
        else:
            start_date = get_first_day(ref_date)
        end_date = get_last_day(start_date)
    # CHỈ lấy đến hôm nay
    end_date = min(end_date, ref_date)
    if end_date < start_date:
        return _columns(), [{"value": 0.0}], None

    # Tính WFH như Present hay không
    count_wfh = cint(filters.get("count_wfh") or 0)
    wfh_sql = " OR a.status = 'Work From Home'" if count_wfh else ""

    # Tổng ngày công
    sql = f"""
        SELECT COALESCE(SUM(
            CASE
                WHEN (a.status = 'Present' {wfh_sql}) THEN 1
                WHEN a.status = 'Half Day' THEN 0.5
                ELSE 0
            END
        ), 0) AS days
        FROM `tabAttendance` a
        WHERE a.employee = %(employee)s
          AND a.attendance_date BETWEEN %(from)s AND %(to)s
          AND a.docstatus = 1
    """
    val = frappe.db.sql(sql, {"employee": employee, "from": start_date, "to": end_date}, as_dict=True)[0].days or 0.0

    return _columns(), [{"value": float(val)}], None


def _columns():
    # Number Card sẽ lấy cột đầu tiên 'value'
    return [{
        "label": "Attendance Days (to date)",
        "fieldname": "value",
        "fieldtype": "Float",
        "width": 150,
    }]
