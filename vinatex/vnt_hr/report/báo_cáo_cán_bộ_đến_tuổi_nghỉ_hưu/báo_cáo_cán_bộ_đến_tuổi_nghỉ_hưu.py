import frappe
from frappe.utils import getdate

def execute(filters=None):
    filters = filters or {}
    cols = get_columns()
    data = get_data(filters)
    return cols, data

def get_columns():
    return [
        {"label": "Mã NV",          "fieldname": "name",                "fieldtype": "Link", "options": "Employee",   "width": 120},
        {"label": "Tên nhân viên",  "fieldname": "employee_name",       "fieldtype": "Data",                           "width": 220},
        {"label": "Phòng ban",      "fieldname": "department",          "fieldtype": "Link", "options": "Department", "width": 200},
        {"label": "Chức danh",      "fieldname": "designation",         "fieldtype": "Link", "options": "Designation","width": 180},
        {"label": "Ngày sinh",      "fieldname": "date_of_birth",       "fieldtype": "Date",                           "width": 120},
        {"label": "Ngày nghỉ hưu",  "fieldname": "date_of_retirement",  "fieldtype": "Date",                           "width": 140},
        {"label": "Còn (ngày)",     "fieldname": "days_until",          "fieldtype": "Int",                            "width": 100},
        {"label": "Giới tính",      "fieldname": "gender",              "fieldtype": "Data",                           "width": 90},
        {"label": "Email",          "fieldname": "company_email",       "fieldtype": "Data",                           "width": 180},
        {"label": "SĐT",            "fieldname": "cell_number",         "fieldtype": "Data",                           "width": 120},
    ]

def get_data(filters):
    # Lấy và chuẩn hóa khoảng ngày
    if not filters.get("from_date") or not filters.get("to_date"):
        return []
    start = getdate(filters["from_date"])
    end   = getdate(filters["to_date"])
    if start > end:
        start, end = end, start

    conditions = [
        "e.status = 'Active'",
        "e.date_of_retirement IS NOT NULL",
        "e.date_of_retirement BETWEEN %(start)s AND %(end)s",
    ]
    params = {"start": start, "end": end}

    if filters.get("company"):
        conditions.append("e.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("department"):
        conditions.append("e.department = %(department)s")
        params["department"] = filters["department"]

    # Map gender linh hoạt
    g = (filters.get("gender") or "").strip()
    if g and g not in ("Tất cả", "Tat ca", "All", "all", ""):
        gender_map = {"Nam": "Male", "Nữ": "Female", "Male": "Male", "Female": "Female"}
        g_std = gender_map.get(g, g)
        conditions.append("e.gender = %(gender)s")
        params["gender"] = g_std

    where_sql = " AND ".join(conditions)

    sql = f"""
        SELECT
            e.name,
            e.employee_name,
            e.department,
            e.designation,
            e.date_of_birth,
            e.date_of_retirement,
            DATEDIFF(e.date_of_retirement, CURDATE()) AS days_until,
            e.gender,
            e.company_email,
            e.cell_number
        FROM `tabEmployee` e
        WHERE {where_sql}
        ORDER BY e.date_of_retirement ASC, e.employee_name ASC
    """
    return frappe.db.sql(sql, params, as_dict=True)
