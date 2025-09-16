# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate

def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = []

    increases = get_increased(filters)
    decreases = get_decreased(filters)

    # đánh số TT và ghép thành 1 dataset
    idx = 1
    for row in increases:
        row["change_type"] = "Lao động tăng"
        data.append(row)

    for row in decreases:
        row["change_type"] = "Lao động giảm"
        data.append(row)

    return columns, data


def get_columns():
    return [
        {"label": "Loại biến động", "fieldname": "change_type", "fieldtype": "Data", "width": 120},
        {"label": "Mã nhân viên", "fieldname": "employee", "fieldtype": "Data", "width": 100},
        {"label": "Họ và tên", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": "Ngày tháng năm sinh", "fieldname": "date_of_birth", "fieldtype": "Date", "width": 120},
        {"label": "Giới tính", "fieldname": "gender", "fieldtype": "Data", "width": 80},
        {"label": "Trình độ học vấn", "fieldname": "education", "fieldtype": "Data", "width": 150},
        {"label": "Thời gian bắt đầu làm việc/nghỉ việc", "fieldname": "change_date", "fieldtype": "Date", "width": 150},
        {"label": "Chức danh", "fieldname": "designation", "fieldtype": "Data", "width": 150},
        {"label": "Bộ phận công tác", "fieldname": "department", "fieldtype": "Data", "width": 150},
        {"label": "Lý do tăng/giảm", "fieldname": "reason", "fieldtype": "Data", "width": 200},
        {"label": "Ghi chú", "fieldname": "note", "fieldtype": "Data", "width": 150},
    ]


def get_increased(filters):
    """Nhân sự mới tuyển trong kỳ"""
    sql = """
        SELECT
            e.name AS employee,
            e.employee_name,
            e.date_of_birth,
            e.gender,
            edu.qualification AS education,
            e.date_of_joining AS change_date,
            e.designation,
            e.department,
            'Tuyển dụng mới' AS reason,
            '' AS note
        FROM `tabEmployee` e
        LEFT JOIN `tabEmployee Education` edu 
            ON edu.parent = e.name
        WHERE e.date_of_joining BETWEEN %(from_date)s AND %(to_date)s
          AND (edu.year_of_passing IS NULL OR edu.year_of_passing = (
                SELECT MAX(edu2.year_of_passing)
                FROM `tabEmployee Education` edu2
                WHERE edu2.parent = e.name
              ))
        ORDER BY e.date_of_joining ASC
    """
    return frappe.db.sql(sql, filters, as_dict=True)


def get_decreased(filters):
    """Nhân sự nghỉ việc trong kỳ"""
    sql = """
        SELECT
            e.name AS employee,
            e.employee_name,
            e.date_of_birth,
            e.gender,
            edu.qualification AS education,
            e.relieving_date AS change_date,
            e.designation,
            e.department,
            'Nghỉ việc' AS reason,
            '' AS note
        FROM `tabEmployee` e
        LEFT JOIN `tabEmployee Education` edu 
            ON edu.parent = e.name
        WHERE e.relieving_date BETWEEN %(from_date)s AND %(to_date)s
          AND (edu.year_of_passing IS NULL OR edu.year_of_passing = (
                SELECT MAX(edu2.year_of_passing)
                FROM `tabEmployee Education` edu2
                WHERE edu2.parent = e.name
              ))
        ORDER BY e.relieving_date ASC
    """
    return frappe.db.sql(sql, filters, as_dict=True)


