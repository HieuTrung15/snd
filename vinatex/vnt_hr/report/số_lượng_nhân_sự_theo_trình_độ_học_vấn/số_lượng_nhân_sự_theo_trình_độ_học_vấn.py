# -*- coding: utf-8 -*-
import frappe
from frappe import _

ORDER = ("Tiến sĩ", "Thạc sĩ", "Đại học", "Trung cấp", "THPT")

def execute(filters=None):
    data = get_data()
    return get_columns(), data, None, get_chart_data(data)

def get_columns():
    return [
        {"label": _("Trình độ học vấn"), "fieldname": "qualification", "fieldtype": "Data", "width": 220},
        {"label": _("Số lượng nhân sự"), "fieldname": "employee_count", "fieldtype": "Int", "width": 150},
    ]

def get_data():
    sql = """
        SELECT
            ee.qualification,
            COUNT(DISTINCT ee.parent) AS employee_count
        FROM `tabEmployee Education` ee
        WHERE ee.custom_check = 1
          AND ee.qualification IN ('Tiến sĩ','Thạc sĩ','Đại học','Trung cấp','THPT')
        GROUP BY ee.qualification
        ORDER BY FIELD(ee.qualification, 'Tiến sĩ','Thạc sĩ','Đại học','Trung cấp','THPT')
    """
    return frappe.db.sql(sql, as_dict=True)

def get_chart_data(data):
    if not data:
        return None
    labels = [r["qualification"] for r in data]
    values = [r["employee_count"] for r in data]
    return {
        "data": {"labels": labels, "datasets": [{"name": "Số nhân sự", "values": values}]},
        "type": "donut",
    }
