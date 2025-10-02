# -*- coding: utf-8 -*-
import json
import frappe
from frappe.utils import get_first_day, get_last_day, today, getdate, cint

def execute(filters=None):
    """
    Tổng số ngày nghỉ trong THÁNG (mặc định tháng hiện tại) cho employee đang login,
    chỉ tính Leave Type: 'Công tác' và 'Nghỉ phép năm'.
    - Cắt phần giao [from_date, to_date]
    - Half Day: nếu half_day_date nằm trong đoạn giao, trừ 0.5 ngày
    Optional filters (JSON):
      {"month": 9, "year": 2025}
      {"from_date": "2025-09-01", "to_date": "2025-09-30"}
      {"employee": "EMP-0001"}
      {"to_today": 1}  # (tuỳ chọn) chỉ tính tới hôm nay
    """

    # --- Parse filters an toàn ---
    if isinstance(filters, str):
        try:
            filters = frappe.parse_json(filters)
        except Exception:
            try:
                filters = json.loads(filters)
            except Exception:
                filters = {}
    filters = filters or {}

    # --- Map user -> employee (RAW SQL, không dính ignore_permissions) ---
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

    # --- Khoảng tính toán ---
    if filters.get("from_date") and filters.get("to_date"):
        start_date = getdate(filters["from_date"])
        end_date   = getdate(filters["to_date"])
    else:
        ref_date = getdate(today())
        month = cint(filters.get("month") or 0)
        year  = cint(filters.get("year")  or 0)
        if month and year:
            start_date = get_first_day(getdate(f"{year:04d}-{month:02d}-01"))
        else:
            start_date = get_first_day(ref_date)
        end_date = get_last_day(start_date)

    # (tuỳ chọn) chỉ lấy tới HÔM NAY
    if cint(filters.get("to_today") or 0):
        end_date = min(end_date, getdate(today()))

    # Quick guard
    if end_date < start_date:
        return _columns(), [{"value": 0.0}], None

    # --- SQL: tính overlap trực tiếp, không subquery ---
    sql = """
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN LEAST(la.to_date,   %(to)s) >= GREATEST(la.from_date, %(from)s) THEN
                        (DATEDIFF(LEAST(la.to_date, %(to)s), GREATEST(la.from_date, %(from)s)) + 1)
                        - CASE
                            WHEN la.half_day = 1
                                 AND la.half_day_date BETWEEN GREATEST(la.from_date, %(from)s)
                                                         AND LEAST(la.to_date,   %(to)s)
                            THEN 0.5 ELSE 0
                          END
                    ELSE 0
                END
            ), 0) AS days
        FROM `tabLeave Application` la
        WHERE la.employee   = %(employee)s
          AND la.docstatus  = 1
          AND la.status     = 'Approved'
          AND la.leave_type IN ('Công tác','Nghỉ phép năm')
          AND la.from_date <= %(to)s
          AND la.to_date   >= %(from)s
    """
    params = {"employee": employee, "from": start_date, "to": end_date}
    res = frappe.db.sql(sql, params, as_dict=True)
    value = float(res[0].days or 0.0)

    return _columns(), [{"value": value}], None


def _columns():
    # Number Card sẽ lấy cột đầu tiên 'value'
    return [{
        "label": "Số ngày nghỉ (Công tác + Phép năm)",
        "fieldname": "value",
        "fieldtype": "Float",
        "width": 160,
    }]
