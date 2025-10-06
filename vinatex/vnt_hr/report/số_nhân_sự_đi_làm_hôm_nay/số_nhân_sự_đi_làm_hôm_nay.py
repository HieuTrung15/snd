import frappe
from frappe.utils import nowdate, getdate

def execute(filters=None):
    filters = filters or {}
    the_date = getdate(nowdate())
    employee = filters.get("employee")
    department = filters.get("department")

    columns = get_columns()
    data = get_data(the_date, employee, department)

    return columns, data

def get_columns():
    return [
        {
            "label": "Mã Nhân sự",
            "fieldname": "employee",
            "fieldtype": "Data",
            "options": "Employee",
            "width": 120
        },
        {
            "label": "Tên Nhân sự",
            "fieldname": "employee_name",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": "Phòng ban",
            "fieldname": "department",
            "fieldtype": "Data",
            "options": "Department",
            "width": 300
        },
        {
            "label": "Giờ checkin",
            "fieldname": "first_in",
            "fieldtype": "Datetime",
            "width": 200
        },
        {
            "label": "Giờ checkout",
            "fieldname": "last_out",
            "fieldtype": "Datetime",
            "hidden": 1,
            "width": 200
        },
        {
            "label": "Số lần chấm công",
            "fieldname": "checkins",
            "fieldtype": "Int",
            "hidden": 1,
            "width": 100
        },
        {
            "label": "Có mặt",
            "fieldname": "present",
            "fieldtype": "Data",
            "width": 90
        },
        {
            "label": "Đếm",
            "fieldname": "count",
            "fieldtype": "Int",
            "width": 1,
            "hidden": 1
        },
    ]

def get_data(the_date, employee=None, department=None):
    # Lấy tất cả nhân viên có ít nhất 1 bản ghi checkin trong ngày
    # và tổng hợp giờ vào/ra
    # Lưu ý: DATE(ec.time) dùng theo timezone DB
    conditions = ["DATE(ec.time) = %(date)s"]
    params = {"date": the_date}

    if employee:
        conditions.append("ec.employee = %(employee)s")
        params["employee"] = employee

    if department:
        conditions.append("e.department = %(department)s")
        params["department"] = department

    where_clause = " AND ".join(conditions)

    query = f"""
        SELECT
            ec.employee AS employee,
            e.employee_name AS employee_name,
            e.department AS department,
            MIN(CASE WHEN ec.log_type = 'IN' THEN ec.time END) AS first_in,
            MAX(CASE WHEN ec.log_type = 'OUT' THEN ec.time END) AS last_out,
            1 as count,
            COUNT(ec.name) AS checkins
        FROM `tabEmployee Checkin` ec
        INNER JOIN `tabEmployee` e ON e.name = ec.employee
        WHERE {where_clause}
        GROUP BY ec.employee, e.employee_name, e.department
        ORDER BY first_in ASC, e.department, e.employee_name
    """

    rows = frappe.db.sql(query, params, as_dict=True)

    # Đặt cột "Có mặt" = "Có" nếu có bất kỳ checkin nào trong ngày
    for r in rows:
        r["present"] = "Có" if (r.get("checkins") or 0) > 0 else "Không"

    return rows
