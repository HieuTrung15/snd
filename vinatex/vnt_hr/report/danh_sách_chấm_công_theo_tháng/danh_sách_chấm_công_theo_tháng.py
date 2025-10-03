from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import get_first_day, get_last_day, getdate, today

def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": _("Mã nhân viên"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": _("Tên nhân viên"), "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": _("Phòng ban"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 200},
        {"label": _("Công ty"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 250},
        {"label": _("Giờ Checkin"), "fieldname": "time", "fieldtype": "Datetime", "width": 270},
    ]

def _get_date_range(filters):
    """Ưu tiên from_date/to_date; nếu thiếu thì dùng tháng hiện tại."""
    if filters.get("from_date") and filters.get("to_date"):
        from_date = getdate(filters.get("from_date"))
        to_date = getdate(filters.get("to_date"))
    else:
        ref = getdate(today())
        from_date = get_first_day(ref)
        to_date = get_last_day(ref)
    # Chuẩn hóa sang string để bind vào SQL (cover 00:00:00 -> 23:59:59)
    from_dt = f"{from_date} 00:00:00"
    to_dt = f"{to_date} 23:59:59"
    return from_dt, to_dt

def get_data(filters):
    from_dt, to_dt = _get_date_range(filters)

    conds = ["ec.time BETWEEN %(from_dt)s AND %(to_dt)s"]
    params = {"from_dt": from_dt, "to_dt": to_dt}

    if filters.get("employee"):
        conds.append("ec.employee = %(employee)s")
        params["employee"] = filters["employee"]

    if filters.get("department"):
        conds.append("emp.department = %(department)s")
        params["department"] = filters["department"]

    if filters.get("company"):
        conds.append("emp.company = %(company)s")
        params["company"] = filters["company"]

    where_clause = " AND ".join(conds)

    sql = f"""
        SELECT
            ec.employee,
            emp.employee_name,
            emp.department,
            emp.company,
            ec.time
        FROM `tabEmployee Checkin` ec
        LEFT JOIN `tabEmployee` emp ON emp.name = ec.employee
        WHERE {where_clause}
        ORDER BY ec.time DESC
    """
    return frappe.db.sql(sql, params, as_dict=True)
