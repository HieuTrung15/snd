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

        {"label": "Ngày hết hạn HĐ",  "fieldname": "contract_end_date",  "fieldtype": "Date",                            "width": 150},
        {"label": "Còn (ngày)",       "fieldname": "days_to_expiry",     "fieldtype": "Int",                             "width": 100},

        {"label": "Email",            "fieldname": "email",              "fieldtype": "Data",                            "width": 180},
        {"label": "SĐT",              "fieldname": "phone",              "fieldtype": "Data",                            "width": 120},
    ]

def get_data(filters):
    # Không có bảng thì trả rỗng

    # # Mặc định: hôm nay -> +30 ngày
    start_date = getdate(today())
    end_date   = getdate(add_days(today(), 30))

    # Ghi đè theo filter nếu có
    if filters.get("from_date"):
        start_date = getdate(filters["from_date"])
    if filters.get("to_date"):
        end_date = getdate(filters["to_date"])

    # Nếu người dùng nhập ngược, tự hoán đổi
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    conditions = [
        "c.validity = 1 ",
        "c.to_date IS NOT NULL",
        "c.to_date BETWEEN %(start)s AND %(end)s",
        "e.status = %(status)s",
    ]
    params = {
        "start": start_date,
        "end": end_date,
        "status": "Active",
    }

    if filters.get("employee"):
        conditions.append("e.employee = %(employee)s")
        params["employee"] = filters["employee"]

    if filters.get("department"):
        conditions.append("e.department = %(department)s")
        params["department"] = filters["department"]

    where_clause = " AND ".join(conditions)

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
        WHERE {where_clause}

    """
    return frappe.db.sql(sql,params, as_dict=True)
