# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_first_day, get_last_day, getdate


class VNTMonthlyPayroll(Document):
    pass


@frappe.whitelist()
def get_active_employees(company=None, branch=None):
    """Return active employees filtered by company and branch (if provided)."""
    filters = {"status": "Active"}
    if company:
        filters["company"] = company
    if branch:
        filters["branch"] = branch

    return frappe.get_all(
        "Employee",
        filters=filters,
        fields=[
            "name",
            "employee_name",
            "designation",
            "company",
            "branch",
            "employment_type",
            "custom_party_member",
            "custom_relation_number",
        ],
        order_by="employee_name asc",
    )


@frappe.whitelist()
def compute_item(employee, company=None, month=None, year=None):
    """Tính các tham số dùng cho bảng lương theo kỳ (month, year) và employee."""
    if not month or not year:
        return {}

    # 1) Xác định kỳ
    month_str = str(int(month)).zfill(2)
    period_start = getdate(f"{year}-{month_str}-01")
    period_end = get_last_day(period_start)

    # 2) Lấy tham số lương đang hiệu lực (ưu tiên from_date mới nhất trong khoảng)
    salary_param = frappe.get_all(
        "VNT Salary Parameter",
        filters={
            "from_date": ("<=", period_start),
            "to_date": (">=", period_end),
            "docstatus": 1,
        },
        fields=[
            "name",
            "reference_salary",
            "regional_minimum_wage",
            "corporate_minimum_wage",
            "meal_allowance",
            "travel_allowance",
            "giam_tru_npt",
            "giam_tru_gia_canh",
        ],
        order_by="from_date desc",
        limit_page_length=1,
    )
    if not salary_param:
        frappe.throw("Không tìm thấy bản ghi Tham số lương hiệu lực cho kỳ tính lương này!")
    param = salary_param[0]

    # 3) Tổng hợp Attendance trong kỳ
    #    - Half Day tính 0.5
    #    - 'Ngày công' nếu status = Present
    #        hoặc Half Day nhưng không gắn leave_type
    #    - Còn lại: lấy nhóm từ Leave Type.custom_leave_group
    #    - Có thể lọc theo company nếu Attendance có cột company
    cond_company = "AND a.company = %(company)s" if company else ""
    sql = f"""
        SELECT
            CASE
                WHEN a.status = 'Present' THEN 'Ngày công'
                WHEN a.status = 'Half Day' AND (a.leave_type IS NULL OR a.leave_type = '') THEN 'Ngày công'
                ELSE COALESCE(lt.custom_leave_group, 'Khác')
            END AS grp,
            SUM(CASE WHEN a.status = 'Half Day' THEN 0.5 ELSE 1 END) AS qty
        FROM `tabAttendance` a
        LEFT JOIN `tabLeave Type` lt ON lt.name = a.leave_type
        WHERE a.employee = %(employee)s
          AND a.docstatus = 1
          AND a.attendance_date BETWEEN %(start)s AND %(end)s
          {cond_company}
        GROUP BY
            CASE
                WHEN a.status = 'Present' THEN 'Ngày công'
                WHEN a.status = 'Half Day' AND (a.leave_type IS NULL OR a.leave_type = '') THEN 'Ngày công'
                ELSE COALESCE(lt.custom_leave_group, 'Khác')
            END
    """
    params = {
        "employee": employee,
        "start": period_start,
        "end": period_end,
    }
    if company:
        params["company"] = company

    rows = frappe.db.sql(sql, params, as_dict=True)
    group_counts = {r.grp: float(r.qty or 0) for r in rows}

    so_phep = group_counts.get("Nghỉ phép", 0.0)
    so_ngay_nghi_vr = group_counts.get("Nghỉ có hưởng lương, chế độ", 0.0)
    nghi_kluong_bhxh_1 = group_counts.get("Nghỉ việc riêng không hưởng lương", 0.0)
    nghi_kluong_bhxh_2 = group_counts.get("Nghỉ hưởng chế độ BHXH", 0.0)
    ngay_cong = group_counts.get("Ngày công", 0.0)

    # 4) Bậc thuế TNCN (child table)
    #    Sắp xếp theo from_cur tăng dần, chuẩn hoá 'to' = 0 => None (không giới hạn)
    brackets = frappe.get_all(
        "VNT Salary Parameter Item",
        filters={"parent": param.name},
        fields=["percent", "from_cur", "to_cur"],
        order_by="from_cur asc, percent asc",
    )
    tax_brackets = []
    for b in brackets:
        rate = float(b.percent or 0)
        frm = float(b.from_cur or 0)
        to_ = float(b.to_cur or 0)
        tax_brackets.append({
            "rate": rate,          # phần trăm, ví dụ 5, 10, ...
            "from": frm,           # VND
            "to": None if to_ == 0 else to_,  # None = không giới hạn
        })

    return {
        "reference_salary": param.reference_salary,
        "regional_minimum_wage": param.regional_minimum_wage,
        "corporate_minimum_wage": param.corporate_minimum_wage,
        "meal_allowance": param.meal_allowance,
        "travel_allowance": param.travel_allowance,
        "so_phep": so_phep,
        "so_ngay_nghi_vr": so_ngay_nghi_vr,
        "nghi_kluong_bhxh": (nghi_kluong_bhxh_1 or 0) + (nghi_kluong_bhxh_2 or 0),
        "ngaycong": ngay_cong,
        "tax_brackets": tax_brackets,
        "giam_tru_npt": param.giam_tru_npt,
        "giam_tru_gia_canh": param.giam_tru_gia_canh,
    }
