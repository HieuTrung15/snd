# vinatex/api/attendance.py  (ví dụ)
import frappe
import json
from frappe.utils import get_first_day, get_last_day, getdate, today, cint

@frappe.whitelist()
def get_attendance_days_this_month(filters=None):
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

    try:
        # --- Map user -> Employee bằng RAW SQL (không dùng ignore_permissions) ---
        row = frappe.db.sql(
            """SELECT name FROM `tabEmployee`
               WHERE user_id=%s AND status='Active' LIMIT 1""",
            (frappe.session.user,),
        )
        employee = filters.get("employee") or (row[0][0] if row else None)
        if not employee:
            return 0.0

        # --- Khoảng: đầu tháng -> HÔM NAY (không kéo hết tháng) ---
        ref_date = getdate(today())
        month = cint(filters.get("month") or 0)
        year  = cint(filters.get("year")  or 0)
        if month and year:
            start_date = get_first_day(getdate(f"{year:04d}-{month:02d}-01"))
        else:
            start_date = get_first_day(ref_date)
        end_date = min(get_last_day(start_date), ref_date)

        # --- WFH tính như Present? ---
        count_wfh = cint(filters.get("count_wfh") or 0)
        wfh_sql = " OR a.status = 'Work From Home'" if count_wfh else ""

        # --- Tính tổng ngày công (Present=1, Half Day=0.5, WFH tùy chọn) ---
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
        res = frappe.db.sql(sql, {"employee": employee, "from": start_date, "to": end_date}, as_dict=True)
        return float(res[0].days or 0.0)

    except Exception:
        # Không để rơi lỗi làm card biến mất
        frappe.log_error(frappe.get_traceback(), "get_attendance_days_this_month failed")
        return 0.0
