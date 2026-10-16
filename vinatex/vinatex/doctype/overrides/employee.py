from __future__ import unicode_literals


import re
import frappe
from datetime import date, datetime
import calendar
from frappe.utils import getdate, now_datetime, today
from dateutil.relativedelta import relativedelta
from erpnext.setup.doctype.employee.employee import (
    Employee
)

# sửa lấy abbr theo company
EMPLOYEE_NAME_PADDING = 5
CURRENT_DIRECTOR_DESIGNATION = "Giám đốc"


def _get_custom_abbr(doc) -> str:
    company_abbr = ""
    if doc.get("company"):
        company_abbr = (frappe.db.get_value("Company", doc.company, "abbr") or "").strip()

    # Luôn ưu tiên abbr theo company để tránh giữ giá trị custom_abbr cũ trên form.
    custom_abbr = company_abbr or (doc.get("custom_abbr") or "").strip()
    if custom_abbr and (doc.get("custom_abbr") or "").strip() != custom_abbr:
        doc.custom_abbr = custom_abbr

    if not custom_abbr:
        frappe.throw(frappe._("Thiếu mã viết tắt công ty (custom_abbr) để tạo mã nhân sự."))

    return custom_abbr


def _get_next_employee_name(custom_abbr: str) -> str:
    lock_key = f"EMPLOYEE-{custom_abbr}"
    plain_prefix = custom_abbr

    # Lock theo từng custom_abbr để tránh sinh trùng mã khi tạo đồng thời.
    frappe.db.sql(
        "insert ignore into `tabSeries` (`name`, `current`) values (%s, 0)",
        (lock_key,),
    )
    frappe.db.sql(
        "select `current` from `tabSeries` where `name` = %s for update",
        (lock_key,),
    )

    plain_pattern = re.compile(rf"^{re.escape(plain_prefix)}(\d+)$")
    dotted_pattern = re.compile(rf"^\.{re.escape(plain_prefix)}\.(\d+)$")

    rows = frappe.db.sql(
        """
        select `name`
        from `tabEmployee`
        where `name` like %s or `name` like %s
        """,
        (f"{plain_prefix}%", f".{plain_prefix}.%"),
        as_dict=True,
    )

    max_num = 0
    width = EMPLOYEE_NAME_PADDING

    for row in rows:
        current_name = (row.get("name") or "").strip()
        matched = dotted_pattern.match(current_name) or plain_pattern.match(current_name)
        if not matched:
            continue

        number_raw = matched.group(1)
        max_num = max(max_num, int(number_raw))
        width = max(width, len(number_raw))

    next_num = max_num + 1
    frappe.db.sql(
        "update `tabSeries` set `current` = %s where `name` = %s",
        (next_num, lock_key),
    )

    return f"{plain_prefix}{str(next_num).zfill(width)}"


def sync_employee_naming_series_by_company_abbr(doc, method=None):
    custom_abbr = _get_custom_abbr(doc)
    doc.naming_series = f"{custom_abbr}.#####"
    doc.name = _get_next_employee_name(custom_abbr)
    doc.employee = doc.name
    doc.flags.name_set = True
# sửa lấy abbr theo company


class VntEmployee(Employee):
    def autoname(self):
        custom_abbr = _get_custom_abbr(self)
        self.naming_series = f"{custom_abbr}.#####"
        self.name = _get_next_employee_name(custom_abbr)
        self.employee = self.name

    # Giữ nguyên các xử lý sau khi lưu của Employee chuẩn (nested set,
    # User Permission, đồng bộ User...).
    def on_update(self):
        super().on_update()

    def after_insert(self):
        super().after_insert()

    def before_save(self):
        self._append_contract_when_employment_type_changes()

    def validate_date(self):
        """Validate Employee dates without comparing joining and retirement dates."""
        if self.date_of_birth and getdate(self.date_of_birth) > getdate(today()):
            frappe.throw(frappe._("Date of Birth cannot be greater than today."))

        self.validate_from_to_dates("date_of_birth", "date_of_joining")
        self.validate_from_to_dates("date_of_joining", "relieving_date")
        self.validate_from_to_dates("date_of_joining", "contract_end_date")

    # hàm khi validate sẽ tính toán số lượng người phụ thuộc khi có tick is_dependent trong bảng custom_vnt_employee_tax, sau đó gán vào trường custom_relation_number
    def validate(self):
        # Employee chuẩn ghép employee_name và thực hiện các kiểm tra
        # trước khi document được ghi vào database.
        super().validate()
        self.employee_name = " ".join(
            part.strip()
            for part in (self.first_name, self.middle_name, self.last_name)
            if part and part.strip()
        )
        self._validate_contract_terms()
        self._set_retirement_date()
        total_dependent = 0
        for row in self.get("custom_vnt_employee_tax"):
            if row.is_dependent:
                total_dependent += 1
        self.custom_relation_number = total_dependent

    def _set_retirement_date(self):
        if not self.date_of_birth or not self.gender:
            return

        gender = (self.gender or "").strip().lower()
        if gender not in ("male", "nam", "m", "female", "nu", "nữ", "f"):
            return

        self.date_of_retirement = get_retirement_date(self.date_of_birth, self.gender)

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

    def _append_contract_when_employment_type_changes(self):
        """Append the current contract snapshot when Employment Type changes."""
        previous = self.get_doc_before_save()
        previous_employment_type = previous.get("employment_type") if previous else None
        employment_type = self.get("employment_type")

        if not employment_type or employment_type == previous_employment_type:
            return

        director_name = _get_current_director_name(self.get("company"))

        # The form and contract reports expect at most one current contract.
        for row in self.get("custom_vnt_contract") or []:
            if row.get("validity"):
                row.validity = 0

        self.append(
            "custom_vnt_contract",
            {
                "type": employment_type,
                "from_date": self.get("custom_appointment_date"),
                "to_date": self.get("contract_end_date"),
                "job_title": self.get("designation"),
                "employee_name": director_name,
                "validity": 1,
            },
        )


def _get_current_director_name(company: str | None) -> str:
    """Return the active director's display name for the Employee company."""
    if not company:
        frappe.throw(frappe._("Vui lòng chọn Công ty trước khi lưu Loại HĐ."))

    directors = frappe.get_all(
        "Employee",
        filters={
            "company": company,
            "status": "Active",
            "designation": CURRENT_DIRECTOR_DESIGNATION,
        },
        fields=["name", "employee_name"],
        order_by="name asc",
        limit=2,
    )
    if not directors:
        frappe.throw(
            frappe._("Không tìm thấy Giám đốc đang hoạt động của công ty {0}.").format(
                frappe.bold(company)
            )
        )
    if len(directors) > 1:
        frappe.throw(
            frappe._("Công ty {0} có nhiều hơn một Giám đốc đang hoạt động.").format(
                frappe.bold(company)
            )
        )

    return directors[0].employee_name


@frappe.whitelist()
def get_approver_by_department(department):
    approver = frappe.get_value("Department Approver", {"parent": department}, "approver")
    if approver:
        return approver
    return None

# Cập nhật tuổi theo luật VN
@frappe.whitelist()
def get_retirement_date(dob: str | date | datetime, gender: str | None = None, extra_months: int = 0) -> str:
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
