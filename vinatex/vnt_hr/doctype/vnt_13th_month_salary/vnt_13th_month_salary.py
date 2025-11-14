# Copyright (c) 2025, vinatex and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate

MONTH_FIELD_MAP = {idx: f"t{idx}" for idx in range(1, 13)}


class VNT13thMonthSalary(Document):
    @frappe.whitelist()
    def get_emp_list(self):
        """Return employee rows enriched with monthly net salary."""
        return get_employee_monthly_net_pay(
            company=self.company,
            branch=self.branch,
            year=self.year,
        )


@frappe.whitelist()
def get_salary_parameter_for_year(year: int | str | None):
    """Return personal & dependent deduction amounts for a given year."""
    param_doc = _fetch_salary_parameter(year)
    if not param_doc:
        frappe.throw(_("Không tìm thấy Tham số lương hiệu lực cho năm {0}").format(year))
    brackets = []
    for row in sorted(param_doc.items, key=lambda d: flt(d.from_cur or 0)):
        brackets.append(
            {
                "percent": flt(row.percent),
                "from": flt(row.from_cur),
                "to": flt(row.to_cur) if row.to_cur not in (None, "") else None,
            }
        )

    return {
        "giam_tru_gia_canh": flt(param_doc.giam_tru_gia_canh),
        "giam_tru_npt": flt(param_doc.giam_tru_npt),
        "tax_brackets": brackets,
    }


def get_employee_monthly_net_pay(company: str | None, branch: str | None, year: int | str | None):
    """Fetch active employees then pull their monthly net salary from payroll items."""
    if not company:
        frappe.throw(_("Vui lòng chọn Công ty trước khi lấy danh sách nhân sự."))
    if not branch:
        frappe.throw(_("Vui lòng chọn Chi nhánh trước khi lấy danh sách nhân sự."))
    if not year:
        frappe.throw(_("Vui lòng nhập Năm trước khi lấy danh sách nhân sự."))

    year = cint(year)
    if not year:
        frappe.throw(_("Giá trị Năm không hợp lệ."))

    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active", "company": company, "branch": branch},
        fields=["name"],
        order_by="employee_name asc",
        limit_page_length=0,
    )

    if not employees:
        return {"items": [], "sourced_months": []}

    employee_codes = [emp.name for emp in employees]
    payroll_docs = _pick_payroll_docs(company=company, branch=branch, year=year)
    parent_to_month = {doc["name"]: month for month, doc in payroll_docs.items()}

    payroll_rows = []
    if parent_to_month:
        payroll_rows = frappe.get_all(
            "VNT Monthly Payroll Item",
            filters={
                "parent": ("in", list(parent_to_month.keys())),
                "employee": ("in", employee_codes),
            },
            fields=["employee", "parent", "thuc_linh"],
            limit_page_length=0,
        )

    monthly_lookup = {code: {} for code in employee_codes}
    for row in payroll_rows:
        parent = row.parent
        month_idx = parent_to_month.get(parent)
        if not month_idx:
            continue
        monthly_lookup.setdefault(row.employee, {})
        monthly_lookup[row.employee][month_idx] = flt(row.thuc_linh)

    items = []
    for emp in employees:
        code = emp.name
        month_values = monthly_lookup.get(code, {})
        row_payload = {"employee": code}
        total = 0.0
        has_value = False
        value_month_count = 0

        for month_idx, fieldname in MONTH_FIELD_MAP.items():
            amount = month_values.get(month_idx)
            if amount is not None:
                total += amount
                has_value = True
                value_month_count += 1
            row_payload[fieldname] = amount

        if has_value:
            row_payload["tong_luong_di_lam"] = total
            row_payload["binh_quan_thang"] = total / max(value_month_count, 1)
        else:
            row_payload["tong_luong_di_lam"] = None
            row_payload["binh_quan_thang"] = None

        items.append(row_payload)

    sourced_months = sorted(payroll_docs.keys())

    return {"items": items, "sourced_months": sourced_months}


def _pick_payroll_docs(company: str, branch: str, year: int):
    """Pick at most one payroll document per month (prefer submitted, latest)."""
    filters = {
        "company": company,
        "branch": branch,
        "year": year,
        "docstatus": ("!=", 2),
    }

    docs = frappe.get_all(
        "VNT Monthly Payroll",
        filters=filters,
        fields=["name", "month", "docstatus", "modified"],
        order_by="docstatus desc, modified desc",
        limit_page_length=0,
    )

    picked = {}
    for doc in docs:
        month_idx = _coerce_month(doc.get("month"))
        if not month_idx or month_idx in picked:
            continue
        picked[month_idx] = doc
        if len(picked) == 12:
            break
    return picked


def _coerce_month(value):
    try:
        month = int(value)
    except (TypeError, ValueError):
        return None
    if 1 <= month <= 12:
        return month
    return None


def _fetch_salary_parameter(year: int | str | None):
    year = cint(year)
    if not year:
        return None

    target_date = getdate(f"{year}-12-31")
    sql = """
        SELECT
            name,
            giam_tru_gia_canh,
            giam_tru_npt
        FROM `tabVNT Salary Parameter`
        WHERE docstatus = 1
          AND from_date <= %(target_date)s
          AND (to_date IS NULL OR to_date >= %(target_date)s)
        ORDER BY from_date DESC, creation DESC
        LIMIT 1
    """
    result = frappe.db.sql(sql, {"target_date": target_date}, as_dict=True)
    if not result:
        return None
    return frappe.get_doc("VNT Salary Parameter", result[0].name)
