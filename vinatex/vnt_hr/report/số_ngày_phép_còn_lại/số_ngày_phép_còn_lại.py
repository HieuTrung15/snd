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

    # Lấy toàn bộ bản ghi Leave Ledger Entry cho nhân viên đó (không lọc ngày)
    rows = frappe.db.sql("""
        SELECT leaves
        FROM `tabLeave Ledger Entry`
        WHERE employee = %s
          AND leave_type = %s
    """, (emp, leave_type), as_dict=True)

    for r in rows:
        leaves = float(r.leaves or 0)
        if leaves > 0:
            credit += leaves
        else:
            debit += abs(leaves)

    remaining = credit - debit

    # Q1: cộng lại phép năm trước còn dư nếu allocation năm trước đã submit
    if leave_type == "Nghỉ phép năm":
        today = getdate(nowdate())
        if today.month <= 3:
            prev_year = today.year - 1
            prev_allocations = frappe.get_all(
                "Leave Allocation",
                filters={
                    "employee": emp,
                    "leave_type": leave_type,
                    "docstatus": 1,
                    "from_date": (">=", f"{prev_year}-01-01"),
                    "to_date": ("<=", f"{prev_year}-12-31"),
                },
                pluck="name",
            )
            if prev_allocations:
                placeholders = ", ".join(["%s"] * len(prev_allocations))
                expired = frappe.db.sql(
                    f"""
                    SELECT SUM(ABS(leaves)) AS expired
                    FROM `tabLeave Ledger Entry`
                    WHERE employee = %s
                      AND leave_type = %s
                      AND transaction_type = 'Leave Allocation'
                      AND is_expired = 1
                      AND docstatus = 1
                      AND transaction_name IN ({placeholders})
                    """,
                    [emp, leave_type, *prev_allocations],
                    as_dict=True,
                )
                extra_credit = float(expired[0].expired or 0)
                if extra_credit:
                    credit += extra_credit
                    remaining += extra_credit

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
