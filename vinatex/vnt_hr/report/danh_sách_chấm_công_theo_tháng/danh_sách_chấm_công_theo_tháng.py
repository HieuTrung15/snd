from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import get_first_day, get_last_day, getdate, today, add_days

PRIV_ROLES = {"HR User", "System Manager"}

def execute(filters=None):
    filters = filters or {}
    _restrict_scope(filters)
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": _("Mã nhân viên"),   "fieldname": "employee",       "fieldtype": "Data",     "width": 140},
        {"label": _("Tên nhân viên"),  "fieldname": "employee_name",  "fieldtype": "Data",     "width": 180},
        {"label": _("Phòng/ban"),      "fieldname": "department",     "fieldtype": "Data",     "width": 180},
        {"label": _("Công ty"),        "fieldname": "company",        "fieldtype": "Data",     "width": 200},
        {"label": _("Giờ chấm công"),  "fieldname": "time",           "fieldtype": "Datetime", "width": 190},
    ]

def _get_date_range(filters):
    """Tính khoảng ngày nửa-mở [start, end) để tránh lỗi 23:59:59"""
    if filters.get("from_date") and filters.get("to_date"):
        start = getdate(filters["from_date"])
        end   = getdate(filters["to_date"])
    else:
        ref = getdate(today())
        start = get_first_day(ref)
        end   = get_last_day(ref)
    return f"{start} 00:00:00", f"{add_days(end, 1)} 00:00:00"

def _is_privileged_user():
    roles = set(frappe.get_roles(frappe.session.user))
    return bool(PRIV_ROLES & roles)

def _get_employee_of_user():
    return frappe.get_value(
        "Employee",
        {"user_id": frappe.session.user, "status": "Active"},
        "name"
    )


def _restrict_scope(filters):
    """Auto lọc theo Employee của user nếu có."""
    if filters.get("employee"):
        return
    emp = _get_employee_of_user()
    if emp:
        filters["employee"] = emp

def get_data(filters):
    start_dt, end_dt = _get_date_range(filters)

    conds = ["ec.time >= %(start_dt)s", "ec.time < %(end_dt)s"]
    params = {"start_dt": start_dt, "end_dt": end_dt}

    if filters.get("employee"):
        conds.append("ec.employee = %(employee)s")
        params["employee"] = filters["employee"]
    if filters.get("department"):
        conds.append("emp.department = %(department)s")
        params["department"] = filters["department"]
    if filters.get("branch"):
        conds.append("emp.branch = %(branch)s")
        params["branch"] = filters["branch"]
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
        INNER JOIN `tabEmployee` emp ON emp.name = ec.employee
        WHERE {where_clause}
        ORDER BY ec.time DESC
    """
    return frappe.db.sql(sql, params, as_dict=True)
