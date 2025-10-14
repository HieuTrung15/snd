# -*- coding: utf-8 -*-
import frappe
from frappe import _

ORDER = ("Tiến sĩ", "Thạc sĩ", "Đại học", "Trung cấp", "THPT")

def execute(filters=None):
    filters = filters or {}
    data = get_data(filters)
    return get_columns(), data, None, get_chart_data(data)

def get_columns():
    return [
        {"label": _("Trình độ học vấn"), "fieldname": "qualification", "fieldtype": "Data", "width": 220},
        {"label": _("Số lượng nhân sự"), "fieldname": "employee_count", "fieldtype": "Int", "width": 150},
    ]

def get_data(filters):
    where_extra = []
    params = []

    # optional filters
    if filters.get("company"):
        where_extra.append("e.company = %s")
        params.append(filters["company"])
    if filters.get("department"):
        where_extra.append("e.department = %s")
        params.append(filters["department"])

    where_clause = (" AND " + " AND ".join(where_extra)) if where_extra else ""

    sql = f"""
        SELECT
            ee.qualification,
            COUNT(DISTINCT ee.parent) AS employee_count
        FROM `tabEmployee Education` ee
        INNER JOIN `tabEmployee` e ON e.name = ee.parent
        WHERE ee.custom_check = 1
          AND e.status = 'Active'
          AND ee.qualification IN ('Tiến sĩ','Thạc sĩ','Đại học','Trung cấp','THPT')
          {where_clause}
        GROUP BY ee.qualification
        ORDER BY FIELD(
            ee.qualification,
            'Tiến sĩ','Thạc sĩ','Đại học','Trung cấp','THPT'
        )
    """
    return frappe.db.sql(sql, params, as_dict=True)

def get_chart_data(data):
    if not data:
        return None
    labels = [r["qualification"] for r in data]
    values = [r["employee_count"] for r in data]
    return {
        "data": {"labels": labels, "datasets": [{"name": "Số nhân sự", "values": values}]},
        "type": "donut",
    }
