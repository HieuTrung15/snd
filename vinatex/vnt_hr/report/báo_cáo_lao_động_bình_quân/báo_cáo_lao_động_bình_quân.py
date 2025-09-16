# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days
from frappe.utils.data import get_first_day, get_last_day, getdate

def execute(filters=None):
    if not filters:
        filters = {}
    columns = [
        # {"label": "STT", "fieldname": "stt", "fieldtype": "Int", "width": 60},
        {"label": "Tháng", "fieldname": "thang", "fieldtype": "Data", "width": 500},
        {"label": "Ngày", "fieldname": "ngay", "fieldtype": "Data", "width": 100},
        {"label": "Số lao động", "fieldname": "so_ld", "fieldtype": "Int", "width": 300},
    ]

    if not filters.get("from_date"):
         from_date = get_first_day(getdate())  # ngày đầu tháng hiện tại
    else:
        from_date = getdate(filters.get("from_date"))
        
    if filters.get("to_date"):
        _to_date = getdate(filters.get("to_date"))
        to_date = _to_date if _to_date <= getdate() else getdate()
    else:
        to_date = get_last_day(getdate())


    data = []
    idx = 1

    d = from_date
    while d <= to_date:
        # Đếm số lao động tại ngày thứ d
        count = frappe.db.count("Employee", {
            "status": "Active",
            "date_of_joining": ("<=", d),
        })

        data.append({
            "thang": d.strftime("%m/%Y"),
            "ngay": d.strftime("%d"),
            "so_ld": count,
        })
        idx += 1
        d = add_days(d, 1)

    return columns, data

