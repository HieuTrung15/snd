import frappe
from frappe.utils import getdate, nowdate
from datetime import timedelta

def _week_bounds(d=None):
    d = getdate(d or nowdate())            # YYYY-MM-DD
    start = d - timedelta(days=d.weekday())  # Monday
    end   = start + timedelta(days=6)        # Sunday
    return start, end

def execute(filters=None):
    filters = filters or {}

    # Tuần hiện tại nếu không truyền from/to
    if not filters.get("from_date") or not filters.get("to_date"):
        ws, we = _week_bounds()
        filters["from_date"] = filters.get("from_date") or ws
        filters["to_date"]   = filters.get("to_date")   or we

    leave_type = "Công tác"                        # cố định
    department = (filters.get("department") or "").strip()
    from_date  = getdate(filters["from_date"])
    to_date    = getdate(filters["to_date"])

    # Đếm NV có lịch công tác
    q = """
        SELECT COALESCE(COUNT(DISTINCT i.employee), 0) AS total
        FROM `tabVNT Business Trip Request Items` i
        INNER JOIN `tabVNT Leave Application Time` t ON t.parent = i.parent
        INNER JOIN `tabLeave Application` la        ON la.name  = i.parent
        WHERE la.docstatus = 1
          AND la.leave_type = %(leave_type)s
          AND NOT (t.to_date   < DATE(%(from_date)s) OR t.from_date > DATE(%(to_date)s))
          AND (%(department)s  = '' OR i.department  = %(department)s)
    """

    params = {
        "leave_type":  leave_type,
        "from_date":   from_date,
        "to_date":     to_date,
        "department":  department,
    }

    try:
        res = frappe.db.sql(q, params, as_dict=1)
        total = int(res[0]["total"]) if res and res[0]["total"] is not None else 0
    except Exception:
        total = 0 

    columns = [{"label": "Total", "fieldname": "total", "fieldtype": "Int", "width": 120}]
    data = [{"total": total}]
    return columns, data
