# Copyright (c) 2025, vinatex
import frappe
from frappe.utils import getdate, today

BUCKET_SQL = """
CASE
    WHEN TIMESTAMPDIFF(MONTH, e.date_of_joining, %(as_of)s) < 12 THEN 'Dưới 1 năm'
    WHEN TIMESTAMPDIFF(YEAR,  e.date_of_joining, %(as_of)s) BETWEEN 1 AND 2 THEN '1-3 năm'
    WHEN TIMESTAMPDIFF(YEAR,  e.date_of_joining, %(as_of)s) BETWEEN 3 AND 4 THEN '3-5 năm'
    WHEN TIMESTAMPDIFF(YEAR,  e.date_of_joining, %(as_of)s) BETWEEN 5 AND 9 THEN '5-10 năm'
    ELSE 'Trên 10 năm'
END
"""

def execute(filters=None):
    if not filters:
        filters = {}

    as_of = getdate(filters.get("as_of_date") or today())
    company = filters.get("company")
    department = filters.get("department")

    params = {"as_of": as_of}
    where = ["e.status = 'Active'", "e.date_of_joining IS NOT NULL"]
    if company:
        where.append("e.company = %(company)s")
        params["company"] = company
    if department:
        where.append("e.department = %(department)s")
        params["department"] = department
    where_sql = " AND ".join(where)

    detail_sql = f"""
        SELECT
            e.name AS employee,
            e.employee_name,
            e.company,
            e.department,
            e.designation,
            e.date_of_joining,
            ROUND(TIMESTAMPDIFF(MONTH, e.date_of_joining, %(as_of)s)/12, 1) AS seniority_years,
            {BUCKET_SQL} AS seniority_bucket
        FROM `tabEmployee` e
        WHERE {where_sql}
        ORDER BY e.company, e.department, e.employee_name
    """
    rows = frappe.db.sql(detail_sql, params, as_dict=True)

    summary_sql = f"""
        SELECT {BUCKET_SQL} AS bucket, COUNT(*) AS cnt
        FROM `tabEmployee` e
        WHERE {where_sql}
        GROUP BY bucket
    """
    raw = frappe.db.sql(summary_sql, params, as_dict=True)
    order = ["Dưới 1 năm", "1-3 năm", "3-5 năm", "5-10 năm", "Trên 10 năm"]
    counts = {r.bucket: r.cnt for r in raw}
    values = [counts.get(b, 0) for b in order]

    chart = {
        "data": {
            "labels": order,
            "datasets": [{"name": "Số nhân sự", "values": values}],
        },
        "type": "bar",
        "barOptions": {"stacked": 0},
    }

    report_summary = [
        {"label": "Dưới 1 năm",  "value": values[0], "indicator": "green"},
        {"label": "1-3 năm",     "value": values[1], "indicator": "green"},
        {"label": "3-5 năm",     "value": values[2], "indicator": "blue"},
        {"label": "5-10 năm",    "value": values[3], "indicator": "orange"},
        {"label": "Trên 10 năm", "value": values[4], "indicator": "red"},
    ]
    return get_columns(), rows, None, chart, report_summary

def get_columns():
    return [
        {"label": "Mã NV",        "fieldname": "employee",        "fieldtype": "Link", "options": "Employee",  "width": 110},
        {"label": "Họ và tên",    "fieldname": "employee_name",   "fieldtype": "Data",                          "width": 180},
        {"label": "Công ty",      "fieldname": "company",         "fieldtype": "Link", "options": "Company",   "width": 160},
        {"label": "Phòng ban",    "fieldname": "department",      "fieldtype": "Link", "options": "Department","width": 160},
        {"label": "Chức danh",    "fieldname": "designation",     "fieldtype": "Data",                          "width": 150},
        {"label": "Ngày vào làm", "fieldname": "date_of_joining", "fieldtype": "Date",                          "width": 120},
        {"label": "Thâm niên (năm)", "fieldname": "seniority_years", "fieldtype": "Float",                      "width": 130},
        {"label": "Nhóm thâm niên",  "fieldname": "seniority_bucket", "fieldtype": "Data",                      "width": 130},
    ]
