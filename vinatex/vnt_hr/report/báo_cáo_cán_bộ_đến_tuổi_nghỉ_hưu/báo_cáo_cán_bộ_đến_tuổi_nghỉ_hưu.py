# Copyright (c) 2025, vinatex
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, add_months, today

def execute(filters=None):
    if not filters:
        filters = {}

    # Defaults
    as_of = getdate(filters.get("as_of_date") or today())
    months_ahead = int(filters.get("months_ahead") or 6)
    age_male = int(filters.get("age_male") or 62)
    age_female = int(filters.get("age_female") or 60)
    include_overdue = int(filters.get("include_overdue") or 0)

    # Tính khoảng thời gian tìm kiếm
    start_date = as_of
    end_date = getdate(add_months(as_of, months_ahead))

    # Validate
    if end_date < start_date:
        frappe.throw("Khoảng thời gian không hợp lệ: 'Đến ngày' nhỏ hơn 'Từ ngày'.")

    columns = get_columns()
    data = get_data(
        start_date=start_date,
        end_date=end_date,
        as_of=as_of,
        age_male=age_male,
        age_female=age_female,
        department=filters.get("department"),
        company=filters.get("company"),
        gender=filters.get("gender"),
        include_overdue=include_overdue,
    )

    return columns, data


def get_columns():
    return [
        {"label": "Mã NV", "fieldname": "employee", "fieldtype": "Data", "options": "Employee", "width": 110},
        {"label": "Họ và tên", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": "Giới tính", "fieldname": "gender", "fieldtype": "Data", "width": 80},
        {"label": "Ngày sinh", "fieldname": "date_of_birth", "fieldtype": "Date", "width": 110},
        {"label": "Tuổi (tại ngày chốt)", "fieldname": "age_now", "fieldtype": "Int", "width": 130},
        {"label": "Tuổi nghỉ hưu (quy định)", "fieldname": "retirement_age", "fieldtype": "Int", "width": 160},
        {"label": "Ngày đến tuổi nghỉ hưu", "fieldname": "retirement_date", "fieldtype": "Date", "width": 160},
        {"label": "Còn lại (ngày)", "fieldname": "days_until", "fieldtype": "Int", "width": 110},
        {"label": "Chức danh", "fieldname": "designation", "fieldtype": "Data", "width": 150},
        {"label": "Phòng ban", "fieldname": "department", "fieldtype": "Data", "options": "Department", "width": 160},
        {"label": "Công ty", "fieldname": "company", "fieldtype": "Data", "options": "Company", "width": 160},
        {"label": "Ghi chú", "fieldname": "note", "fieldtype": "Data", "width": 180},
    ]


def get_data(
    start_date,
    end_date,
    as_of,
    age_male,
    age_female,
    department=None,
    company=None,
    gender=None,
    include_overdue=0,
):
    params = {
        "start_date": start_date,
        "end_date": end_date,
        "as_of": as_of,
        "age_male": age_male,
        "age_female": age_female,
    }

    where = ["e.status = 'Active'"]  # chỉ nhân viên đang làm việc

    # Lọc công ty/phòng ban nếu có
    if company:
        where.append("e.company = %(company)s")
        params["company"] = company
    if department:
        where.append("e.department = %(department)s")
        params["department"] = department

    # Lọc giới tính (chấp nhận cả tiếng Việt & tiếng Anh)
    if gender and gender not in ("Tất cả", "All", ""):
        if gender in ("Nam", "Male"):
            where.append("e.gender in ('Nam','Male')")
        elif gender in ("Nữ", "Female"):
            where.append("e.gender in ('Nữ','Nu','Female')")

    # CASE tuổi nghỉ hưu theo giới
    retirement_age_case = """
        CASE
            WHEN e.gender IN ('Nam','Male') THEN %(age_male)s
            WHEN e.gender IN ('Nữ','Nu','Female') THEN %(age_female)s
            ELSE %(age_male)s
        END
    """

    # Ngày nghỉ hưu = ngày sinh + tuổi nghỉ hưu (năm)
    retirement_date_expr = f"DATE_ADD(e.date_of_birth, INTERVAL {retirement_age_case} YEAR)"

    # điều kiện thời gian:
    # - nếu include_overdue = 1: cho phép retirement_date <= as_of (quá hạn) hoặc trong [start_date, end_date]
    # - nếu include_overdue = 0: chỉ lấy trong [start_date, end_date]
    if include_overdue:
        time_filter = f"(({retirement_date_expr} <= %(as_of)s) OR ({retirement_date_expr} BETWEEN %(start_date)s AND %(end_date)s))"
    else:
        time_filter = f"({retirement_date_expr} BETWEEN %(start_date)s AND %(end_date)s)"

    where.append(time_filter)
    where_sql = " AND ".join(where)

    sql = f"""
        SELECT
            e.name AS employee,
            e.employee_name,
            e.gender,
            e.date_of_birth,
            e.designation,
            e.department,
            e.company,

            -- tuổi hiện tại tại ngày chốt
            TIMESTAMPDIFF(YEAR, e.date_of_birth, %(as_of)s) AS age_now,

            {retirement_age_case} AS retirement_age,
            {retirement_date_expr} AS retirement_date,

            DATEDIFF({retirement_date_expr}, %(as_of)s) AS days_until,

            '' AS note
        FROM `tabEmployee` e
        WHERE {where_sql}
        ORDER BY {retirement_date_expr} ASC, e.department, e.employee_name
    """

    rows = frappe.db.sql(sql, params, as_dict=True)
    return rows
