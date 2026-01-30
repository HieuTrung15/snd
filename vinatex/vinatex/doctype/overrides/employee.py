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
    # hàm khi validate sẽ tính toán số lượng người phụ thuộc khi có tick is_dependent trong bảng custom_vnt_employee_tax, sau đó gán vào trường custom_relation_number
    def validate(self):
        self._validate_contract_terms()
        total_dependent = 0
        for row in self.get("custom_vnt_employee_tax"):
            if row.is_dependent:
                total_dependent += 1
        self.custom_relation_number = total_dependent

    def _validate_contract_terms(self):
        """Chỉ cho nhập số trong trường 'Thời hạn HĐ (tháng)' của bảng custom_vnt_contract."""
        for row in self.get("custom_vnt_contract") or []:
            val = row.get("contract_term")
            if val in (None, ""):
                continue
            try:
                int(str(val))
            except (TypeError, ValueError):
                frappe.throw(
                    frappe._("Dòng {0}: Thời hạn HĐ (tháng) phải là số nguyên.").format(row.idx),
                    title=frappe._("Lỗi dữ liệu"),
                )
        

@frappe.whitelist()
def get_approver_by_department(department):
    approver = frappe.get_value("Department Approver", {"parent": department}, "approver")
    if approver:
        return approver
    return None

# Cập nhật tuổi theo luật VN
@frappe.whitelist()
def get_retirement_date(dob: str, gender: str | None = None, extra_months: int = 0) -> str:
    """
    Tính NGÀY nghỉ hưu theo lộ trình VN, KHÓA THEO NĂM ĐỦ TUỔI (không dựa năm hiện tại).
    - Nam: 60y3m (2021) +3m/năm, trần 62y (>=2028).
    - Nữ: 55y4m (2021) +4m/năm, trần 60y (>=2035).
    Trả về NGÀY ĐẦU TIÊN CỦA THÁNG KẾ TIẾP SAU KHI ĐỦ TUỔI (YYYY-MM-DD).
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

    def first_day_next_month(dt):
        # Ví dụ: 2025-10-15 -> 2025-11-01
        return dt.replace(day=1) + relativedelta(months=+1)

    # Chọn năm sớm nhất mà NGÀY ĐỦ TUỔI rơi đúng năm đó theo lộ trình
    earliest_anniv = d + relativedelta(months=+(base_2021 + extra_months))
    latest_anniv = d + relativedelta(months=+(cap + extra_months))
    start_year = max(2021, earliest_anniv.year - 1)
    end_year = max(start_year, latest_anniv.year + 2)

    for year in range(start_year, end_year + 1):
        m = months_for_year(year)
        anniv = d + relativedelta(months=+(m + extra_months))
        if anniv.year == year:
            return first_day_next_month(anniv).isoformat()

    # Fallback: nếu không khớp năm (trường hợp đã quá tuổi trước 2021)
    return first_day_next_month(earliest_anniv).isoformat()


@frappe.whitelist()
def get_employee_for_current_user():
    """Lấy mã nhân viên liên kết với user hiện tại. Dùng cho html block trang chủ"""
    user = frappe.session.user
    if not user:
        return ""

    emp_code = frappe.db.get_value("Employee", {"user_id": user}, "name")

    return emp_code or ""
