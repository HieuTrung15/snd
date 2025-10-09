from __future__ import unicode_literals


import frappe
from datetime import date
import calendar
from frappe.utils import getdate, now_datetime
from dateutil.relativedelta import relativedelta
from erpnext.setup.doctype.employee.employee import (
    Employee
)



class VntEmployee(Employee):
    pass

@frappe.whitelist()
def get_approver_by_department(department):
    approver = frappe.get_value("Department Approver", {"parent": department}, "approver")
    if approver:
        return approver
    return None

# Cập nhật tuổi theo luật VN
@frappe.whitelist()
def get_retirement_date(dob: str, gender: str | None = None) -> str:
    """
    Tính NGÀY nghỉ hưu theo lộ trình VN, KHÓA THEO NĂM NGHỈ HƯU (không dựa năm hiện tại).
    - Nam: 60y3m (2021) +3m/năm, trần 62y (>=2028).
    - Nữ: 55y4m (2021) +4m/năm, trần 60y (>=2035).
    Trả về ngày cuối tháng đủ tuổi (YYYY-MM-DD).
    extra_months: cộng/trừ tháng cho diện đặc thù (âm nếu nghỉ sớm hợp lệ).
    """
    d = getdate(dob)
    g = (gender or "").strip().lower()

    if g in ("male", "nam", "m"):
        base_2021, inc_per_year, cap = 60*12 + 3, 3, 62*12
    elif g in ("female", "nu", "nữ", "f"):
        base_2021, inc_per_year, cap = 55*12 + 4, 4, 60*12
    else:
        frappe.throw("Giới tính không hợp lệ. Vui lòng chọn lại!")

    def months_for_year(Y: int) -> int:
        # Tuổi hưu (tháng) áp dụng trong NĂM Y theo lộ trình, chặn trần
        months = base_2021 + max(0, Y - 2021) * inc_per_year
        return min(months, cap)

    # Bước 1: ước lượng bằng trần (để không bị thiếu), rồi "khóa" theo năm về hưu
    retired = d + relativedelta(months=+cap)
    for _ in range(8):  # vài vòng là hội tụ
        m = months_for_year(retired.year)
        r2 = d + relativedelta(months=+m)
        if r2 == retired:
            break
        retired = r2

    retired = retired
    return retired.isoformat()