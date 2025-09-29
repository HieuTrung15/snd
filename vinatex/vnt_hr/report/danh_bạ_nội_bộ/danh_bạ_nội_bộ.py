# apps/vinatex/vinatex/vnt_hr/report/danh_bạ_nội_bộ/danh_bạ_nội_bộ.py
from __future__ import unicode_literals
from frappe import _
import frappe

def execute(filters=None):
    filters = filters or {}
    columns = get_columns(filters)
    data = get_data(filters)
    return columns, data, None

def get_columns(filters=None):
    return [
        {"label": _("Mã số Nhân sự"), "fieldname": "employee", "fieldtype": "Data", "width": 120},
        {"label": _("Tên Nhân sự"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
        {"label": _("Chức danh"), "fieldname": "designation", "fieldtype": "Data", "width": 120},
        {"label": _("Phòng/Ban"), "fieldname": "department", "fieldtype": "Data", "width": 200},
        {"label": _("Công ty"), "fieldname": "company", "fieldtype": "Data", "width": 250},
        {"label": _("Chi nhánh"), "fieldname": "branch", "fieldtype": "Data", "width": 120},
        {"label": _("Số điện thoại"), "fieldname": "phone", "fieldtype": "Data", "width": 140},
        {"label": _("Email"), "fieldname": "company_email", "fieldtype": "Data", "width": 200},
    ]

def get_data(filters=None):
    where_sql, params = build_emp_conditions(filters)
    sql = f"""
        SELECT
            emp.name            AS employee,
            emp.employee_name   AS employee_name,
            emp.designation     AS designation,
            emp.department      AS department,
            emp.company         AS company,
            emp.branch          AS branch,
            emp.cell_number     AS phone,
            emp.company_email   AS company_email
        FROM `tabEmployee` emp
        WHERE emp.status != 'Left'
            {where_sql}
        ORDER BY emp.employee_name
    """
    return frappe.db.sql(sql, params, as_dict=True)

def build_emp_conditions(filters=None):
    conds = []
    params = {}

    if filters.get("employee"):
        conds.append("AND emp.name = %(employee)s")   
        params["employee"] = filters["employee"]

    if filters.get("company"):
        conds.append("AND emp.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("department"):
        conds.append("AND emp.department = %(department)s")
        params["department"] = filters["department"]

    where_sql = " ".join(conds)
    return where_sql, params

def build_cpn_conditions(filters):
    conds = []
    params = {}

    if filters.get("company"):
        conds.append("cpn.name = %(company)s")
        params["company"] = filters["company"]

    where_sql = f"WHERE {' AND '.join(conds)}" if conds else ""
    return where_sql, params
