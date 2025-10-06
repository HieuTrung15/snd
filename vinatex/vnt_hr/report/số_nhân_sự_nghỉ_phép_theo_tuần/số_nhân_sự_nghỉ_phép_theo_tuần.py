# file: erpnext/[app_name]/[module]/report/so_nhan_su_nghi_phep_theo_tuan/so_nhan_su_nghi_phep_theo_tuan.py
import frappe
from frappe.utils import getdate, add_days, nowdate

def execute(filters=None):
    filters = filters or {}

    # Xác định tuần hiện tại dựa trên "hôm nay"
    ref_date = getdate(nowdate())

    def week_bounds(d):
        # ISO: Monday=1..Sunday=7
        iso_weekday = d.isocalendar()[2]
        mon = add_days(d, -(iso_weekday - 1))
        sun = add_days(mon, 6)
        return mon, sun

    week_start, week_end = week_bounds(ref_date)

    # Lấy Leave Application đã duyệt, có giao thoa với tuần hiện tại,
    # và leave_type khác 'công tác' (không phân biệt hoa/thường)
    leave_apps = frappe.db.sql(
        """
        SELECT
            name,
            employee,
            employee_name,
            from_date,
            to_date,
            leave_type
        FROM `tabLeave Application`
        WHERE
            docstatus = 1
            AND (from_date <= %(week_end)s AND to_date >= %(week_start)s)
            AND (LOWER(COALESCE(leave_type, '')) <> 'công tác')
        """,
        {
            "week_start": week_start,
            "week_end": week_end,
        },
        as_dict=True,
    )

    # Đếm DISTINCT nhân sự có nghỉ trong tuần
    employees = {la.employee for la in leave_apps if la.employee}
    headcount = len(employees)


    data = [{
        "week_start": week_start,
        "week_end": week_end,
        "headcount": headcount,
    }]

    columns = [
        {"label": "Từ ngày", "fieldname": "week_start", "fieldtype": "Date", "width": 110},
        {"label": "Đến ngày", "fieldname": "week_end", "fieldtype": "Date", "width": 110},
        {"label": "Số nhân sự nghỉ", "fieldname": "headcount", "fieldtype": "Int", "width": 140},
    ]

    message = ""

    return columns, data, message
