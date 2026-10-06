import frappe
from frappe import _
from frappe.utils import add_days, getdate, today

from vinatex.api.hr_dashboard import _normalize_branches


@frappe.whitelist()
def get_hr_reminders(
    days_ahead: int = 30,
    limit: int = 100,
    include_retirements: int = 1,
    branches=None,
    branch: str | None = None,
    as_of_date: str | None = None,
    company: str | None = None,
):
    if not frappe.has_permission("Employee", "read"):
        frappe.throw(_("Bạn không có quyền xem dữ liệu nhân sự."), frappe.PermissionError)

    days_ahead = max(1, min(int(days_ahead or 30), 365))
    limit = max(1, min(int(limit or 100), 500))
    start = getdate(as_of_date or today())
    current_date = getdate(today())
    if start > current_date:
        frappe.throw(_("Ngày dữ liệu không được lớn hơn ngày hiện tại."))

    end = getdate(add_days(start, days_ahead))
    end_retire = getdate(add_days(start, 365))
    branches = _normalize_branches(branches or branch)
    company = (company or frappe.defaults.get_user_default("Company") or "").strip()

    if start == current_date:
        employee_active_condition = "e.status = 'Active'"
    else:
        employee_active_condition = (
            "e.date_of_joining <= %(start)s "
            "AND (e.relieving_date IS NULL OR e.relieving_date > %(start)s)"
        )

    branch_condition = " AND e.branch IN %(branches)s" if branches else ""
    company_condition = " AND e.company = %(company)s" if company else ""
    params = {
        "start": start,
        "end": end,
        "end_retire": end_retire,
        "branches": branches,
        "company": company,
    }

    contracts = frappe.db.sql(
        """
        SELECT
            c.name,
            c.employee,
            e.employee_name,
            e.department,
            c.to_date AS end_date
        FROM `tabVNT Contract` c
        LEFT JOIN `tabEmployee` e ON e.name = c.parent
        WHERE c.validity = 1
          AND {employee_active_condition}
          AND c.to_date IS NOT NULL
          AND c.to_date BETWEEN %(start)s AND %(end)s
          {branch_condition}
          {company_condition}
        ORDER BY c.to_date ASC
        """.format(
            employee_active_condition=employee_active_condition,
            branch_condition=branch_condition,
            company_condition=company_condition,
        ),
        params,
        as_dict=True,
    )

    birthdays = frappe.db.sql(
        """
        SELECT
            e.name AS employee,
            e.employee_name,
            e.department,
            e.date_of_birth,
            CASE
              WHEN STR_TO_DATE(CONCAT(YEAR(%(start)s), '-', DATE_FORMAT(e.date_of_birth, '%%m-%%d')), '%%Y-%%m-%%d') >= %(start)s
              THEN STR_TO_DATE(CONCAT(YEAR(%(start)s), '-', DATE_FORMAT(e.date_of_birth, '%%m-%%d')), '%%Y-%%m-%%d')
              ELSE DATE_ADD(STR_TO_DATE(CONCAT(YEAR(%(start)s), '-', DATE_FORMAT(e.date_of_birth, '%%m-%%d')), '%%Y-%%m-%%d'), INTERVAL 1 YEAR)
            END AS next_birthday
        FROM `tabEmployee` e
        WHERE {employee_active_condition}
          AND e.date_of_birth IS NOT NULL
          {branch_condition}
          {company_condition}
        HAVING next_birthday BETWEEN %(start)s AND %(end)s
        ORDER BY next_birthday ASC
        """.format(
            employee_active_condition=employee_active_condition,
            branch_condition=branch_condition,
            company_condition=company_condition,
        ),
        params,
        as_dict=True,
    )

    retirements = []
    if int(include_retirements or 0):
        retirement_age = int(frappe.db.get_single_value("HR Settings", "retirement_age") or 60)
        retirement_params = {**params, "ret_age": retirement_age}
        retirements = frappe.db.sql(
            """
            SELECT
                e.name AS employee,
                e.employee_name,
                e.department,
                e.date_of_birth,
                COALESCE(
                    e.date_of_retirement,
                    DATE_ADD(e.date_of_birth, INTERVAL %(ret_age)s YEAR)
                ) AS date_of_retirement
            FROM `tabEmployee` e
            WHERE {employee_active_condition}
              AND e.date_of_birth IS NOT NULL
              AND COALESCE(
                    e.date_of_retirement,
                    DATE_ADD(e.date_of_birth, INTERVAL %(ret_age)s YEAR)
                  ) BETWEEN %(start)s AND %(end_retire)s
              {branch_condition}
              {company_condition}
            ORDER BY date_of_retirement ASC
            """.format(
                employee_active_condition=employee_active_condition,
                branch_condition=branch_condition,
                company_condition=company_condition,
            ),
            retirement_params,
            as_dict=True,
        )

    return {
        "params": {
            "start": str(start),
            "end": str(end),
            "days_ahead": days_ahead,
            "branches": list(branches),
            "company": company,
        },
        "counts": {
            "contracts": len(contracts),
            "birthdays": len(birthdays),
            "retirements": len(retirements),
        },
        "contracts_expiring": contracts[:limit],
        "birthdays": birthdays[:limit],
        "retirements": retirements[:limit],
    }
