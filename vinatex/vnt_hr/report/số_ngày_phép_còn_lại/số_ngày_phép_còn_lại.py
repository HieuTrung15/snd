import frappe
from frappe.utils import getdate, nowdate

def execute(filters=None):
    filters = filters or {}
    user = frappe.session.user
    leave_type = filters.get("leave_type") or "Nghỉ phép năm"

    # Lấy thông tin nhân viên hiện tại
    emp_info = frappe.db.get_value(
        "Employee",
        {"user_id": user, "status": "Active"},
        ["name", "employee_name"],
        as_dict=True
    )

    if not emp_info:
        return [], [], None

    emp = emp_info.name
    emp_name = emp_info.employee_name
    credit = debit = 0.0

    today = getdate(nowdate())
    year_start = f"{today.year}-01-01"
    year_end = f"{today.year}-12-31"

    # Số được cấp = Leave Allocation năm nay (docstatus=1)
    credit = float(
        frappe.db.sql(
            """
            SELECT SUM(total_leaves_allocated) AS allocated
            FROM `tabLeave Allocation`
            WHERE employee = %s
              AND leave_type = %s
              AND docstatus = 1
              AND from_date >= %s
              AND to_date <= %s
            """,
            (emp, leave_type, year_start, year_end),
            as_dict=True,
        )[0].allocated
        or 0
    )

    # Q1: cộng thêm Leave Allocation của năm trước
    if leave_type == "Nghỉ phép năm" and today.month <= 3:
        prev_year = today.year - 1
        prev_year_start = f"{prev_year}-01-01"
        prev_year_end = f"{prev_year}-12-31"
        prev_alloc = float(
            frappe.db.sql(
                """
                SELECT SUM(total_leaves_allocated) AS allocated
                FROM `tabLeave Allocation`
                WHERE employee = %s
                  AND leave_type = %s
                  AND docstatus = 1
                  AND from_date >= %s
                  AND to_date <= %s
                """,
                (emp, leave_type, prev_year_start, prev_year_end),
                as_dict=True,
            )[0].allocated
            or 0
        )
        credit += prev_alloc

    # Số đã dùng = Leave Application trong năm hiện tại
    debit = float(
        frappe.db.sql(
            """
            SELECT SUM(ABS(leaves)) AS used
            FROM `tabLeave Ledger Entry`
            WHERE employee = %s
              AND leave_type = %s
              AND transaction_type = 'Leave Application'
              AND docstatus = 1
              AND from_date >= %s
              AND to_date <= %s
            """,
            (emp, leave_type, year_start, year_end),
            as_dict=True,
        )[0].used
        or 0
    )

    remaining = credit - debit

    data = [{
        "employee_name": emp_name,
        "leave_type": leave_type,
        "allocated": credit,
        "used": debit,
        "remaining": remaining
    }]

    columns = [
        {"label": "Tên nhân viên", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "Loại phép", "fieldname": "leave_type", "fieldtype": "Data", "width": 150},
        {"label": "Số được cấp", "fieldname": "allocated", "fieldtype": "Float", "width": 110},
        {"label": "Số đã dùng", "fieldname": "used", "fieldtype": "Float", "width": 110},
        {"label": "Số còn lại", "fieldname": "remaining", "fieldtype": "Float", "width": 120},
    ]

    return columns, data, None
