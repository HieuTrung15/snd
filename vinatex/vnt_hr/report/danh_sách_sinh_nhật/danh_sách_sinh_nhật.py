import frappe
from frappe.utils.data import getdate, today

def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data

def get_columns():
    return [
        {"label": "Mã NV", "fieldname": "employee_code", "fieldtype": "Data", "width": 120},
        {"label": "Tên nhân viên", "fieldname": "employee_name", "fieldtype": "Data", "width": 250},
        {"label": "Phòng ban", "fieldname": "department", "fieldtype": "Data", "width": 300},
        {"label": "Chức danh", "fieldname": "designation", "fieldtype": "Data", "width": 300},
        {"label": "Ngày sinh", "fieldname": "dob", "fieldtype": "Date", "width": 120},
        {"label": "Tuổi", "fieldname": "age", "fieldtype": "Int", "width": 80},
        {"label": "Email", "fieldname": "email", "fieldtype": "Data", "width": 150},
        {"label": "Số điện thoại", "fieldname": "phone", "fieldtype": "Data", "width": 120},
    ]

def get_data(filters):
    conditions = []

    if filters.get("from_date") and filters.get("to_date"):
        conditions.append(
            f"DATE_FORMAT(emp.date_of_birth, '%m-%d') BETWEEN DATE_FORMAT('{filters.get('from_date')}', '%m-%d') AND DATE_FORMAT('{filters.get('to_date')}', '%m-%d')"
        )
    if filters.get("department"):
        conditions.append(f"emp.department = '{filters.get('department')}'")
    if filters.get("employee"):
        conditions.append(f"emp.name = '{filters.get('employee')}'")

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = " AND " + where_clause

    sql = f"""
        SELECT
            emp.name AS employee_code,
            emp.employee_name,
            emp.department,
            emp.designation,
            emp.date_of_birth AS dob,
            emp.company_email AS email,
            emp.cell_number AS phone,
            FLOOR(DATEDIFF(CURDATE(), emp.date_of_birth)/365) AS age
        FROM
            `tabEmployee` emp
        WHERE emp.status = 'Active' {where_clause}
        ORDER BY MONTH(emp.date_of_birth), DAY(emp.date_of_birth)
    """

    data = frappe.db.sql(sql, as_dict=True)
    return data
