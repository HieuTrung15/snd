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

    # lấy tham số lương đang hiệu lực
    param = frappe.db.get_value(
        "VNT Salary Parameter",
        filters={
            "from_date": ("<=", period_start),
            "to_date": (">=", period_end),
            "docstatus": 1
        },
        fieldname=[
            "name",
            "reference_salary",
            "regional_minimum_wage",
            "corporate_minimum_wage",
            "meal_allowance",
            "travel_allowance",
            "giam_tru_npt",
            "giam_tru_gia_canh",

        ],
        as_dict=True
    )

    if not param:
        frappe.throw("Không tìm thấy bản ghi Tham số lương hiệu lực cho kỳ tính lương này!")

    # lấy số ngày phép của nhân viên trong kỳ
    sql = """
    SELECT 
        CASE 
            WHEN a.status = 'Present' THEN 'Ngày công'
            ELSE lt.custom_leave_group
        END AS custom_leave_group,
        COUNT(*) AS cnt
    FROM `tabAttendance` a
    LEFT JOIN `tabLeave Type` lt ON a.leave_type = lt.name
    WHERE a.employee = %(employee)s
      AND a.docstatus = 1
      AND a.attendance_date BETWEEN %(start)s AND %(end)s
    GROUP BY 
        CASE 
            WHEN a.status = 'Present' THEN 'Ngày công'
            ELSE lt.custom_leave_group
        END
    """
    result = frappe.db.sql(sql, {
        "employee": employee,
        "start": period_start,
        "end": period_end,
    }, as_dict=True)

    group_counts = {r.custom_leave_group: r.cnt for r in result if r.custom_leave_group}

    so_phep = group_counts.get("Nghỉ phép", 0)
    so_ngay_nghi_vr = group_counts.get("Nghỉ có hưởng lương, chế độ", 0)
    nghi_kluong_bhxh_1 = group_counts.get("Nghỉ việc riêng không hưởng lương", 0)
    nghi_kluong_bhxh_2 = group_counts.get("Nghỉ hưởng chế độ BHXH", 0)
    ngay_cong = group_counts.get("Ngày công", 0)


    # lấy bảng con thuế thu nhập cá nhân lũy tiến
    # Lấy các bậc thuế từ child table
    brackets = frappe.get_all(
        "VNT Salary Parameter Item",
        filters={"parent": param.name},
        fields=["percent", "from_cur", "to_cur"],
        order_by="percent asc",
    )
    tax_brackets = [
        {
            "rate": float(b.percent or 0),     # % thuế, ví dụ 5, 10...
            "from": float(b.from_cur or 0),    # VND
            "to": float(b.to_cur or 0),        # 0 = không giới hạn
        }
        for b in brackets
    ]

    return {
        "reference_salary": param.reference_salary,
        "regional_minimum_wage": param.regional_minimum_wage,
        "corporate_minimum_wage": param.corporate_minimum_wage,
        "meal_allowance": param.meal_allowance,
        "travel_allowance": param.travel_allowance,
        "so_phep": so_phep,
        "so_ngay_nghi_vr": so_ngay_nghi_vr,
        "nghi_kluong_bhxh": nghi_kluong_bhxh_1 + nghi_kluong_bhxh_2,
        "ngaycong": ngay_cong,
        "tax_brackets": tax_brackets,
        "giam_tru_npt": param.giam_tru_npt,
        "giam_tru_gia_canh": param.giam_tru_gia_canh
    }
