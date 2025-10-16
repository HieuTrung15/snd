import frappe
from frappe.utils import getdate, add_days, nowdate


@frappe.whitelist()
def execute(filters=None):
    filters = filters or {}
    mode = (filters.get("mode") or "detail").lower()

    ref_date = getdate(nowdate())

    def week_bounds(d):
        iso_weekday = d.isocalendar()[2]
        mon = add_days(d, -(iso_weekday - 1))
        sun = add_days(mon, 6)
        return mon, sun

    week_start, week_end = week_bounds(ref_date)

    if mode == "summary":
        rows = frappe.db.sql(
            """
            SELECT
                la.employee,
                la.employee_name,
                e.branch,
                -- tổng ngày nghỉ trong tuần (đã cắt + trừ half-day nếu có)
                SUM(
                    DATEDIFF(LEAST(la.to_date, %(week_end)s), GREATEST(la.from_date, %(week_start)s)) + 1
                    - CASE
                        WHEN IFNULL(la.half_day, 0) = 1
                             AND la.half_day_date BETWEEN
                                 GREATEST(la.from_date, %(week_start)s)
                                 AND LEAST(la.to_date, %(week_end)s)
                        THEN 0.5 ELSE 0
                      END
                ) AS days_off,
                1 AS headcount
            FROM `tabLeave Application` la
            JOIN `tabEmployee` e ON e.name = la.employee
            WHERE la.docstatus = 1
              AND la.from_date <= %(week_end)s
              AND la.to_date   >= %(week_start)s
            GROUP BY la.employee, la.employee_name
            HAVING days_off > 0
            ORDER BY la.employee_name
            """,
            {"week_start": week_start, "week_end": week_end},
            as_dict=True,
        )

        data = [
            {
                "employee": r.employee,
                "employee_name": r.employee_name,
                "days_off": float(round(r.days_off or 0, 1)),
                "headcount": 1
            }
            for r in rows
        ]

        total_headcount = len(data)
        total_days = sum(d["days_off"] for d in data)

        columns = [
            {"label": "Mã NV", "fieldname": "employee", "fieldtype": "Data", "width": 120},
            {"label": "Tên nhân viên", "fieldname": "employee_name", "fieldtype": "Data", "width": 220},
            {"label": "Tổng ngày nghỉ (tuần)", "fieldname": "days_off", "fieldtype": "Float", "precision": 1, "width": 160},
            {"label": "Số nhân sự", "fieldname": "headcount", "fieldtype": "Int", "width": 120}
        ]
        return columns, data, f"Tổng nhân sự nghỉ: <b>{total_headcount}</b> • Tổng ngày nghỉ: <b>{total_days}</b>"

    rows = frappe.db.sql(
        """
        SELECT
            la.name AS leave_app,
            la.employee,
            la.employee_name,
            e.branch,
            la.leave_type,
            la.custom_leave_group as leave_group,
            GREATEST(la.from_date, %(week_start)s) AS actual_from,
            LEAST(la.to_date, %(week_end)s) AS actual_to,
            (
                DATEDIFF(LEAST(la.to_date, %(week_end)s), GREATEST(la.from_date, %(week_start)s)) + 1
                - CASE
                    WHEN IFNULL(la.half_day, 0) = 1
                         AND la.half_day_date BETWEEN
                             GREATEST(la.from_date, %(week_start)s)
                             AND LEAST(la.to_date, %(week_end)s)
                    THEN 0.5 ELSE 0
                  END
            ) AS days_off
        FROM `tabLeave Application` la
        JOIN `tabEmployee` e ON e.name = la.employee
        WHERE la.docstatus = 1
          AND la.from_date <= %(week_end)s
          AND la.to_date   >= %(week_start)s
        ORDER BY la.employee_name, actual_from
        """,
        {"week_start": week_start, "week_end": week_end},
        as_dict=True,
    )

    data = []
    seen = set()  # để đánh dấu nhân sự đã xuất hiện
    for r in rows:
        days = float(round((r.days_off or 0.0), 1))
        if days <= 0:
            continue
        first_of_emp = 0
        if r.employee and r.employee not in seen:
            first_of_emp = 1
            seen.add(r.employee)
        data.append({
            "employee": r.employee,
            "employee_name": r.employee_name,
            "branch": r.branch,
            "leave_type": r.leave_type,
            "from_date": r.actual_from,
            "to_date": r.actual_to,
            "days_off": days,
            "leave_app": r.leave_app,
            "headcount": first_of_emp,
            "leave_group": r.leave_group
        })

    total_headcount = sum(d["headcount"] for d in data)

    columns = [
        {"label": "Mã NV", "fieldname": "employee", "fieldtype": "Data", "width": 120},
        {"label": "Tên nhân viên", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "Chi nhánh", "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 200},
        {"label": "Nhóm nghỉ phép", "fieldname": "leave_group", "fieldtype": "Data", "width": 250},
        {"label": "Loại nghỉ phép", "fieldname": "leave_type", "fieldtype": "Data", "width": 150},
        {"label": "Từ ngày", "fieldname": "from_date", "fieldtype": "Date", "width": 110},
        {"label": "Đến ngày", "fieldname": "to_date", "fieldtype": "Date", "width": 110},
        {"label": "Số ngày nghỉ", "fieldname": "days_off", "fieldtype": "Float", "precision": 1, "width": 120},
        {"label": "Số nhân sự", "fieldname": "headcount", "fieldtype": "Int", "width": 110, "hidden": 1}
    ]

    return columns, data, f"Tổng phiếu nghỉ: <b>{len(data)}</b> • Tổng nhân sự: <b>{total_headcount}</b>"
