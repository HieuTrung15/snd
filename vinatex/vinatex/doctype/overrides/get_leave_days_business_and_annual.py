import frappe
from frappe.utils import get_first_day, get_last_day, today, getdate, cint

@frappe.whitelist()
def get_leave_days_business_and_annual(filters=None):
    # Parse filters
    if isinstance(filters, str):
        try:
            filters = frappe.parse_json(filters)
        except Exception:
            filters = None
    filters = filters or {}

    # Map user -> employee
    employee = filters.get("employee") or frappe.db.get_value(
        "Employee", {"user_id": frappe.session.user, "status": "Active"}, "name", ignore_permissions=True
    )
    if not employee:
        return 0.0

    # Khoảng tính toán
    if filters.get("from_date") and filters.get("to_date"):
        start_date = getdate(filters["from_date"])
        end_date   = getdate(filters["to_date"])
    else:
        ref_date = getdate(today())
        month = cint(filters.get("month") or 0)
        year  = cint(filters.get("year")  or 0)
        if month and year:
            start_date = get_first_day(getdate(f"{year:04d}-{month:02d}-01"))
        else:
            start_date = get_first_day(ref_date)
        end_date = get_last_day(start_date)

    # Quick guard: nếu from > to thì 0
    if end_date < start_date:
        return 0.0

    # SQL: trực tiếp tính overlap, không tạo subquery
    sql = """
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN LEAST(la.to_date,   %(to)s) >= GREATEST(la.from_date, %(from)s) THEN
                        (DATEDIFF(LEAST(la.to_date, %(to)s), GREATEST(la.from_date, %(from)s)) + 1)
                        - CASE
                            WHEN la.half_day = 1
                                 AND la.half_day_date BETWEEN GREATEST(la.from_date, %(from)s)
                                                         AND LEAST(la.to_date,   %(to)s)
                            THEN 0.5 ELSE 0
                          END
                    ELSE 0
                END
            ), 0) AS days
        FROM `tabLeave Application` la
        WHERE la.employee   = %(employee)s
          AND la.docstatus  = 1
          AND la.status     = 'Approved'
          AND la.leave_type IN ('Công tác','Nghỉ phép năm')
          AND la.from_date <= %(to)s
          AND la.to_date   >= %(from)s
    """
    params = {"employee": employee, "from": start_date, "to": end_date}
    res = frappe.db.sql(sql, params, as_dict=True)
    return float(res[0].days or 0.0)
