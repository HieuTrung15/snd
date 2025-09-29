# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, today

def execute(filters=None):
    if not filters:
        filters = {}

    # default to_date = hôm nay nếu chưa truyền
    if not filters.get("to_date"):
        filters["to_date"] = today()

    columns = get_columns()
    data = []

    change = (filters.get("change") or "Tất cả").strip()

    # Tùy loại biến động để lấy dữ liệu
    if change in ("Tất cả", ""):
        increases = get_increased(filters)
        for row in increases:
            row["change_type"] = "Lao động tăng"
            data.append(row)

        decreases = get_decreased(filters)
        for row in decreases:
            row["change_type"] = "Lao động giảm"
            data.append(row)

    elif change == "Lao động tăng":
        increases = get_increased(filters)
        for row in increases:
            row["change_type"] = "Lao động tăng"
            data.append(row)

    elif change == "Lao động giảm":
        decreases = get_decreased(filters)
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
        {"label": "Thời gian bắt đầu làm việc/nghỉ việc", "fieldname": "change_date", "fieldtype": "Date", "width": 180},
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
        WHERE ( %(from_date)s IS NULL OR e.date_of_joining >= %(from_date)s )
            AND ( %(to_date)s   IS NULL OR e.date_of_joining <= %(to_date)s )
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
        WHERE ( %(from_date)s IS NULL OR e.date_of_joining >= %(from_date)s )
            AND ( %(to_date)s   IS NULL OR e.date_of_joining <= %(to_date)s )
          AND (edu.year_of_passing IS NULL OR edu.year_of_passing = (
                SELECT MAX(edu2.year_of_passing)
                FROM `tabEmployee Education` edu2
                WHERE edu2.parent = e.name
              ))
        ORDER BY e.relieving_date ASC
    """
    return frappe.db.sql(sql, filters, as_dict=True)
