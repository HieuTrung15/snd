# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_first_day, get_last_day, getdate

class VNTMonthlyPayroll(Document):
    pass

@frappe.whitelist()
def compute_item(employee, company=None, month=None, year=None):
    if not month or not year:
        return {}
    
    month_str = str(month).zfill(2)
    period_start = getdate(f"{year}-{month_str}-01")
    period_end = get_last_day(period_start)

    param = frappe.db.get_value(
        "VNT Salary Parameter",
        filters={
            "from_date": ("<=", period_start),
            "to_date": (">=", period_end),
            "docstatus": 1
        },
        fieldname=[
            "reference_salary",
            "regional_minimum_wage",
            "corporate_minimum_wage",
            "meal_allowance",
            "travel_allowance",
        ],
        as_dict=True
    )

    if not param:
        frappe.throw("Không tìm thấy bản ghi Tham số lương hiệu lực cho kỳ tính lương này!")

    # so_ngay_phep = frappe.db.get_value(
    #     "Attendance",
    #     filters={
    #         "employee": employee,
    #         "attendance_date": ("between", (period_start, period_end)),

    #     })

    return {
        "reference_salary": param.reference_salary,
        "regional_minimum_wage": param.regional_minimum_wage,
        "corporate_minimum_wage": param.corporate_minimum_wage,
        "meal_allowance": param.meal_allowance,
        "travel_allowance": param.travel_allowance
    }
