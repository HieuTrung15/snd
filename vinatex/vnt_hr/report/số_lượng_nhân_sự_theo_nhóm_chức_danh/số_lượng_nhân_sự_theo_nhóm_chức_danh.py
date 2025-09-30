# -*- coding: utf-8 -*-
import frappe
from frappe import _

def execute(filters=None):
    # filters 
    columns = get_columns()
    data = get_data(filters)
    chart = get_chart_data(data)
    return columns, data, None, chart

def get_columns():
    return [
        {
            "label": _("Nhóm chức danh"),
            "fieldname": "designation_group",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": _("Số lượng nhân sự"),
            "fieldname": "employee_count",
            "fieldtype": "Int",
            "width": 120
        }
    ]

def get_data(filters):
    # lấy dữ liệu từ bảng Employee
    # giả sử field custom_designation_group
    conditions = []
    if filters:
        if filters.get("company"):
            conditions.append(f"employee.company = {frappe.db.escape(filters.get('company'))}")

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # SQL truy vấn nhóm theo nhóm chức danh
    sql = f"""
        SELECT
            employee.custom_designation_group AS designation_group,
            COUNT(*) AS employee_count
        FROM
            `tabEmployee` employee
        {where_clause}
        GROUP BY
            employee.custom_designation_group
        ORDER BY
            COUNT(*) DESC
    """
    rows = frappe.db.sql(sql, as_dict=True)
    for r in rows:
        if not r.designation_group:
            r.designation_group = _("(Không có)")
    return rows

def get_chart_data(data):
    labels = []
    values = []
    for row in data:
        labels.append(row.designation_group)
        values.append(row.employee_count)

    chart = {
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "name": _("Employees"),
                    "values": values
                }
            ]
        },
        "type": "bar",
        "height": 300
    }
    return chart
