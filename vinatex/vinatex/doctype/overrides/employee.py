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
def get_retirement_date(dob: str, gender: str, year: int | None = None) -> str:
    """
    Tính ngày nghỉ hưu theo LUẬT áp dụng của NĂM HIỆN TẠI:
    - Lấy tuổi hưu (tháng) của năm Y (mặc định Y = năm hiện tại).
    - Cộng vào DOB -> ra 'tháng đủ tuổi'.
    - Trả về NGÀY CUỐI THÁNG đủ tuổi (phù hợp NĐ 135).

    Trả về: 'YYYY-MM-DD' (string)
    """
    d = getdate(dob)
    Y = int(year) if year else now_datetime().year  # năm hiện tại của server/site
    if Y < 2021:
        Y = 2021  # lộ trình bắt đầu 2021

    g = (gender or "").strip().lower()
    if g in ("male", "nam", "m"):
        base_2021, inc_per_year, cap = 60*12 + 3, 3, 62*12
    elif g in ("female", "nu", "nữ", "f"):
        base_2021, inc_per_year, cap = 55*12 + 4, 4, 60*12
    else:
        frappe.throw("Giới tính không hợp lệ. Dùng 'nam' hoặc 'nu'.")

    # tuổi hưu (tháng) áp dụng cho NĂM Y
    months = base_2021 + max(0, Y - 2021) * inc_per_year
    months = min(months, cap)

    tmp = d + relativedelta(months=+months)  # ngày đủ tuổi (theo lịch)
    # Thời điểm nghỉ hưu: cuối THÁNG đủ tuổi
    last_day = calendar.monthrange(tmp.year, tmp.month)[1]
    retired = tmp.replace(day=last_day)
    # frappe.throw(retired.isoformat())
    return retired.isoformat()