import frappe
from frappe.utils import getdate, add_days, today

def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": "Mã NV",            "fieldname": "employee",           "fieldtype": "Link", "options": "Employee",   "width": 120},
        {"label": "Tên nhân viên",    "fieldname": "employee_name",      "fieldtype": "Data",                           "width": 220},
        {"label": "Phòng ban",        "fieldname": "department",         "fieldtype": "Link", "options": "Department", "width": 220},
        {"label": "Chức danh",        "fieldname": "designation",        "fieldtype": "Link", "options": "Designation","width": 180},
        {"label": "Ngày hết hạn HĐ",  "fieldname": "contract_end_date",  "fieldtype": "Date",                           "width": 150},
        {"label": "Còn (ngày)",       "fieldname": "days_to_expiry",     "fieldtype": "Int",                             "width": 100},
        {"label": "Email",            "fieldname": "company_email",      "fieldtype": "Data",                            "width": 180},
        {"label": "SĐT",              "fieldname": "cell_number",        "fieldtype": "Data",                            "width": 120},
    ]

def get_data(filters):
    sql = f"""
        SELECT
            e.employee               AS employee,
            e.employee_name          AS employee_name,
            e.department             AS department,
            e.designation            AS designation,
            c.to_date                AS contract_end_date,
            DATEDIFF(c.to_date, CURDATE()) AS days_to_expiry,
            e.company_email          AS email,
            e.cell_number            AS phone
        FROM `tabVNT Contract` c
        LEFT JOIN `tabEmployee` e ON e.name = c.parent
        WHERE c.validity = 1
        ORDER BY c.to_date ASC, e.employee_name ASC
    """
    return frappe.db.sql(sql, as_dict=True)
