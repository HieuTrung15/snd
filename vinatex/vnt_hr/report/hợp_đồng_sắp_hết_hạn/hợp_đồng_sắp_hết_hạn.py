import frappe
from frappe.utils import getdate, add_days, today

def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": "Mã NV", "fieldname": "employee", "fieldtype": "Data", "options": "Employee", "width": 120},
        {"label": "Tên nhân viên", "fieldname": "employee_name", "fieldtype": "Data", "width": 220},
        {"label": "Phòng ban", "fieldname": "department", "fieldtype": "Data", "options": "Department", "width": 220},
        {"label": "Chức danh", "fieldname": "designation", "fieldtype": "Data", "options": "Designation", "width": 180},

        {"label": "Ngày hết hạn HĐ", "fieldname": "contract_end_date", "fieldtype": "Date", "width": 200},
        {"label": "Ngày nghỉ hưu", "fieldname": "date_of_retirement", "fieldtype": "Date", "width": 130},

        {"label": "Còn (ngày)", "fieldname": "days_to_expiry", "fieldtype": "Int", "width": 100},

        {"label": "Trạng thái", "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": "Email", "fieldname": "email", "fieldtype": "Data", "width": 180},
        {"label": "SĐT", "fieldname": "phone", "fieldtype": "Data", "width": 120},
    ]

def _get_window(filters):
    """Xác định khoảng ngày để lọc.
    - Nếu có from_date & to_date: dùng đúng khoảng đó
    - Ngược lại nếu có days_ahead: từ hôm nay → hôm nay + days_ahead
    - Mặc định: 60 ngày tới
    """
    if filters.get("from_date") and filters.get("to_date"):
        return getdate(filters["from_date"]), getdate(filters["to_date"])
    days = int(filters.get("days_ahead") or 60)
    start = getdate(filters.get("base_date") or today())
    end = getdate(add_days(start, days))
    return start, end

def get_data(filters):
    start_date, end_date = _get_window(filters)

    # Biểu thức chọn ngày hết hạn gần nhất giữa contract_end_date và date_of_retirement
    expiry_expr = """
        CASE
            WHEN emp.contract_end_date IS NOT NULL AND emp.date_of_retirement IS NOT NULL
                THEN IF(emp.contract_end_date <= emp.date_of_retirement, emp.contract_end_date, emp.date_of_retirement)
            WHEN emp.contract_end_date IS NOT NULL THEN emp.contract_end_date
            WHEN emp.date_of_retirement IS NOT NULL THEN emp.date_of_retirement
            ELSE NULL
        END
    """

    conditions = []
    params = [start_date, end_date]

    # Lọc theo khoảng ngày của "ngày xét hết hạn"
    conditions.append(f"({expiry_expr}) BETWEEN %s AND %s")

    # Các bộ lọc tùy chọn
    if filters.get("department"):
        conditions.append("emp.department = %s")
        params.append(filters["department"])

    if filters.get("employee"):
        conditions.append("emp.name = %s")
        params.append(filters["employee"])

    #  filter status
    if filters.get("status"):
        conditions.append("emp.status = %s")
        params.append(filters["status"])
    else:
        conditions.append("emp.status = 'Active'")

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT
            emp.name AS employee,
            emp.employee_name,
            emp.department,
            emp.designation,
            emp.contract_end_date,
            emp.date_of_retirement,
            {expiry_expr} AS expiry_date,
            CASE
                WHEN emp.contract_end_date IS NOT NULL AND (emp.date_of_retirement IS NULL OR emp.contract_end_date <= emp.date_of_retirement)
                    THEN 'contract_end_date'
                WHEN emp.date_of_retirement IS NOT NULL AND (emp.contract_end_date IS NULL OR emp.date_of_retirement < emp.contract_end_date)
                    THEN 'date_of_retirement'
                ELSE NULL
            END AS expiry_source,
            DATEDIFF({expiry_expr}, CURDATE()) AS days_to_expiry,
            emp.status,
            emp.personal_email AS email,
            emp.cell_number AS phone
        FROM `tabEmployee` emp
        WHERE {where_clause}
        ORDER BY expiry_date ASC, employee_name ASC
    """

    return frappe.db.sql(sql, params, as_dict=True)
