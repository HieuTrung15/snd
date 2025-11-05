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


def get_employee_contracts(employee, period_start, period_end):
    """Return employment contracts overlapping the requested payroll period."""
    if not employee or not period_start or not period_end:
        return []

    sql = """
        SELECT
            name,
            type,
            contract_no,
            contract_date,
            from_date,
            to_date,
            contract_term,
            validity
        FROM `tabVNT Contract`
        WHERE parent = %(employee)s
          AND parenttype = 'Employee'
          AND parentfield = 'custom_vnt_contract'
          AND (from_date IS NULL OR from_date <= %(period_end)s)
          AND (to_date IS NULL OR to_date >= %(period_start)s)
        ORDER BY
            COALESCE(from_date, DATE('1900-01-01')),
            name
    """
    params = {
        "employee": employee,
        "period_start": period_start,
        "period_end": period_end,
    }
    return frappe.db.sql(sql, params, as_dict=True)


def get_employee_salary_history(employee):
    """Return salary history entries for the employee."""
    if not employee:
        return []

    return frappe.get_all(
        "VNT Employee Salary History",
        filters={
            "parent": employee,
            "parenttype": "Employee",
            "parentfield": "custom_emp_salary_history",
        },
        fields=["name", "he_so", "from_date", "to_date"],
        order_by="from_date asc, creation asc",
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
    attendance_sql = f"""
        SELECT
            a.status,
            a.attendance_date,
            a.leave_type,
            COALESCE(lt.custom_leave_group, 'Khác') AS leave_group
        FROM `tabAttendance` a
        LEFT JOIN `tabLeave Type` lt ON lt.name = a.leave_type
        WHERE a.employee = %(employee)s
          AND a.docstatus = 1
          AND a.attendance_date BETWEEN %(start)s AND %(end)s
          {cond_company}
    """
    params = {
        "employee": employee,
        "start": period_start,
        "end": period_end,
    }
    if company:
        params["company"] = company

    attendance_details = frappe.db.sql(attendance_sql, params, as_dict=True)

    group_counts = {}

    def add_group_qty(group_name, qty):
        if qty and qty != 0:
            group_counts[group_name] = group_counts.get(group_name, 0.0) + float(qty)

    WORKING_STATUS_FULL = {"Present", "Work From Home", "On Duty"}
    for att in attendance_details:
        status = (att.status or "").strip()
        leave_group = att.leave_group or "Khác"
        if status in WORKING_STATUS_FULL:
            add_group_qty("Ngày công", 1.0)
        elif status == "Half Day":
            add_group_qty("Ngày công", 0.5)
            if att.leave_type:
                add_group_qty(leave_group, 0.5)
        else:
            add_group_qty(leave_group, 1.0)

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

    contracts = get_employee_contracts(employee, period_start, period_end)
    baseline_date = getdate("1900-01-01")
    far_future = getdate("9999-12-31")
    salary_history = get_employee_salary_history(employee)

    def ensure_date(value, fallback):
        return getdate(value) if value else fallback

    def find_salary_coefficient(target_date):
        if not target_date or not salary_history:
            return None
        for entry in reversed(salary_history):
            start = ensure_date(entry.get("from_date"), baseline_date)
            end = ensure_date(entry.get("to_date"), far_future)
            if start <= target_date <= end:
                return float(entry.get("he_so") or 0)
        return None

    def annotate_contract(contract):
        if not contract:
            return None, None
        contract_start = ensure_date(contract.get("from_date"), baseline_date)
        contract_end = ensure_date(contract.get("to_date"), far_future)
        overlap_start = max(period_start, contract_start)
        overlap_end = min(period_end, contract_end)
        if overlap_start > overlap_end:
            contract["salary_coefficient"] = None
            return None, None
        contract["salary_coefficient"] = find_salary_coefficient(overlap_start)
        return overlap_start, overlap_end

    contract_types_sorted = sorted(
        contracts,
        key=lambda c: (
            ensure_date(c.get("from_date"), baseline_date),
            c.get("name") or "",
        ),
    )
    current_contract = contract_types_sorted[-1] if contract_types_sorted else None
    previous_contract = (
        contract_types_sorted[-2] if len(contract_types_sorted) > 1 else None
    )
    current_overlap_start, _ = annotate_contract(current_contract)
    previous_overlap_start, _ = annotate_contract(previous_contract)

    current_contract_type = current_contract.get("type") if current_contract else None
    previous_contract_type = previous_contract.get("type") if previous_contract else None
    current_salary_coefficient = find_salary_coefficient(current_overlap_start)
    previous_salary_coefficient = find_salary_coefficient(previous_overlap_start)

    total_working_days = float(ngay_cong or 0)
    previous_working_days = 0.0
    current_working_days = total_working_days

    if (
        current_contract
        and previous_contract
        and current_contract.get("from_date")
    ):
        current_from = getdate(current_contract.get("from_date"))
        if period_start <= current_from <= period_end:
            def working_qty(att_row):
                status_local = (att_row.status or "").strip()
                if status_local in WORKING_STATUS_FULL:
                    return 1.0
                if status_local == "Half Day":
                    return 0.5
                return 0.0

            for att in attendance_details:
                qty = working_qty(att)
                if qty <= 0:
                    continue
                att_date = getdate(att.attendance_date)
                if att_date < current_from:
                    previous_working_days += qty

            if previous_working_days > total_working_days:
                previous_working_days = total_working_days
            current_working_days = total_working_days - previous_working_days

    return {
        "reference_salary": param.reference_salary,
        "regional_minimum_wage": param.regional_minimum_wage,
        "corporate_minimum_wage": param.corporate_minimum_wage,
        "meal_allowance": param.meal_allowance,
        "travel_allowance": param.travel_allowance,
        "so_phep": so_phep,
        "so_ngay_nghi_vr": so_ngay_nghi_vr,
        "nghi_kluong_bhxh": (nghi_kluong_bhxh_1 or 0) + (nghi_kluong_bhxh_2 or 0),
        "tax_brackets": tax_brackets,
        "giam_tru_npt": param.giam_tru_npt,
        "giam_tru_gia_canh": param.giam_tru_gia_canh,
        "contracts": contracts,
        "current_contract_type": current_contract_type,
        "previous_contract_type": previous_contract_type,
        "current_working_days": current_working_days,
        "previous_working_days": previous_working_days,
        "ngaycong": total_working_days,
        "current_salary_coefficient": current_salary_coefficient,
        "previous_salary_coefficient": previous_salary_coefficient,
        "latest_salary_coefficient": find_salary_coefficient(period_end) or find_salary_coefficient(period_start),
    }
