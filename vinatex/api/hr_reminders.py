import frappe
from frappe.utils import getdate, add_days, today

@frappe.whitelist()
def get_hr_reminders(days_ahead: int = 30, limit: int = 100):
    days_ahead = int(days_ahead or 30)
    limit = int(limit)

    start = getdate(today())
    end = getdate(add_days(start, days_ahead))

    # --- HỢP ĐỒNG: VNT Contract ---
    contracts = []
    
    contracts = frappe.db.sql(
        """
        SELECT
            vc.name,
            vc.employee,
            e.employee_name,
            e.department,
            vc.to_date AS end_date
        FROM `tabVNT Contract` vc
        LEFT JOIN `tabEmployee` e ON e.name = vc.employee
        WHERE vc.validity = 1 

        ORDER BY vc.to_date ASC
        LIMIT %(limit)s
        """,
        {"start": start, "end": end, "limit": limit},
        as_dict=True,
    )
    

    # --- SINH NHẬT (như trước) ---
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
        WHERE e.status = 'Active' AND e.date_of_birth IS NOT NULL
        HAVING next_birthday BETWEEN %(start)s AND %(end)s
        ORDER BY next_birthday ASC
        LIMIT %(limit)s
        """,
        {"start": start, "end": end, "limit": limit},
        as_dict=True,
    )

    # --- NGHỈ HƯU (như trước) ---
    retirement_age = frappe.db.get_single_value("HR Settings", "retirement_age") or 60
    retirements = frappe.db.sql(
        """
        SELECT
            e.name AS employee,
            e.employee_name,
            e.department,
            e.date_of_birth,
            DATE_ADD(e.date_of_birth, INTERVAL %(ret_age)s YEAR) AS retirement_date
        FROM `tabEmployee` e
        WHERE e.status = 'Active' AND e.date_of_birth IS NOT NULL
        HAVING retirement_date BETWEEN %(start)s AND %(end)s
        ORDER BY retirement_date ASC
        LIMIT %(limit)s
        """,
        {"ret_age": int(retirement_age), "start": start, "end": end, "limit": limit},
        as_dict=True,
    )

    return {
        "params": {"start": str(start), "end": str(end), "days_ahead": days_ahead, "limit": limit},
        "counts": {
            "contracts": len(contracts),
            "birthdays": len(birthdays),
            "retirements": len(retirements),
        },
        "contracts_expiring": contracts,
        "birthdays": birthdays,
        "retirements": retirements,
    }
