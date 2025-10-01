import frappe
from frappe.utils import getdate, add_days, today

@frappe.whitelist()
def get_hr_reminders(days_ahead: int = 30, limit: int = 100):
    days_ahead = int(days_ahead or 30)
    limit = int(limit)

    start = getdate(today())
    end = getdate(add_days(start, days_ahead))

    # --- HỢP ĐỒNG SẮP HẾT HẠN: lấy từ tabEmployee ---
    # end_date = min(contract_end_date, date_of_retirement) (nếu có cả 2)
    contracts = frappe.db.sql(
        """
        SELECT
            e.name AS employee,
            e.employee_name,
            e.department,
            CASE
                WHEN e.contract_end_date IS NOT NULL AND e.date_of_retirement IS NOT NULL
                    THEN IF(e.contract_end_date <= e.date_of_retirement, e.contract_end_date, e.date_of_retirement)
                WHEN e.contract_end_date IS NOT NULL THEN e.contract_end_date
                WHEN e.date_of_retirement IS NOT NULL THEN e.date_of_retirement
                ELSE NULL
            END AS end_date
        FROM `tabEmployee` e
        WHERE e.status = 'Active'
          AND (e.contract_end_date IS NOT NULL OR e.date_of_retirement IS NOT NULL)
        HAVING end_date BETWEEN %(start)s AND %(end)s
        ORDER BY end_date ASC
        """,
        {"start": start, "end": end},
        as_dict=True,
    )

    # --- SINH NHẬT (giữ nguyên) ---
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
        """,
        {"start": start, "end": end},
        as_dict=True,
    )

    # --- NGHỈ HƯU ---
    # retirement_date = COALESCE(date_of_retirement, date_of_birth + retirement_age năm)
    retirement_age = frappe.db.get_single_value("HR Settings", "retirement_age") or 60
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
            ) AS retirement_date
        FROM `tabEmployee` e
        WHERE e.status = 'Active' AND e.date_of_birth IS NOT NULL
        HAVING retirement_date BETWEEN %(start)s AND %(end)s
        ORDER BY retirement_date ASC
        """,
        {"ret_age": int(retirement_age), "start": start, "end": end},
        as_dict=True,
    )

    return {
        "params": {"start": str(start), "end": str(end), "days_ahead": days_ahead},
        "counts": {
            "contracts": len(contracts),
            "birthdays": len(birthdays),
            "retirements": len(retirements),
        },
        "contracts_expiring": contracts,
        "birthdays": birthdays,
        "retirements": retirements,
    }
