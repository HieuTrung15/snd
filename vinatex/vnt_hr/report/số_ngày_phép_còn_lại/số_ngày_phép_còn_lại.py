import frappe
from frappe.utils import getdate, nowdate

def execute(filters=None):
    filters = filters or {}
    user = frappe.session.user
    leave_type = filters.get("leave_type") or "Nghỉ phép năm"
    today = getdate(nowdate())

    # Lấy employee + employee_name gắn với user hiện tại
    emp_info = frappe.db.get_value(
        "Employee",
        {"user_id": user, "status": "Active"},
        ["name", "employee_name"],
        as_dict=True
    )

    if not emp_info:
        return [
            {"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 160},
            {"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
            {"label": "Leave Type", "fieldname": "leave_type", "fieldtype": "Data", "width": 150},
            {"label": "Được cấp", "fieldname": "allocated", "fieldtype": "Float", "width": 110},
            {"label": "Đã dùng", "fieldname": "used", "fieldtype": "Float", "width": 110},
            {"label": "Còn lại", "fieldname": "remaining", "fieldtype": "Float", "width": 120}
        ], [], None

    emp = emp_info.name
    emp_name = emp_info.employee_name
    credit = debit = 0.0

    # Lấy tất cả bản ghi Ledger có hiệu lực
    rows = frappe.db.sql("""
        SELECT leaves
        FROM `tabLeave Ledger Entry`
        WHERE employee = %s
          AND leave_type = %s
          AND from_date <= %s
          AND to_date >= '2000-01-01'
    """, (emp, leave_type, today), as_dict=True)

    for r in rows:
        leaves = float(r.leaves or 0)
        if leaves > 0:
            credit += leaves
        else:
            debit += abs(leaves)

    remaining = credit - debit

    data = [{
        "employee": emp,
        "employee_name": emp_name,
        "leave_type": leave_type,
        "allocated": credit,
        "used": debit,
        "remaining": remaining
    }]

    columns = [
        # {"label": "Mã nhân viên", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": "Tên nhân viên", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "Loại phép", "fieldname": "leave_type", "fieldtype": "Data", "width": 150},
        {"label": "Số được cấp", "fieldname": "allocated", "fieldtype": "Float", "width": 110},
        {"label": "Số đã dùng", "fieldname": "used", "fieldtype": "Float", "width": 110},
        {"label": "Số còn lại", "fieldname": "remaining", "fieldtype": "Float", "width": 120}
    ]

    return columns, data, None
