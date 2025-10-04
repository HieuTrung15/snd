import frappe
from frappe.utils import today, getdate

def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    rows = get_data(filters)
    chart = make_chart(rows)
    return columns, rows, None, chart

def get_columns():
    return [
        {"label": "Nhóm tuổi", "fieldname": "bucket", "fieldtype": "Data", "width": 180},
        {"label": "Số nhân sự", "fieldname": "count", "fieldtype": "Int", "width": 120},
    ]

def get_data(filters):
    params = {
        "status": filters.get("status") or "Active",
        "today": getdate(today()),
    }
    where = ["e.status = %(status)s"]

    if filters.get("company"):
        where.append("e.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("department"):
        where.append("e.department = %(department)s")
        params["department"] = filters["department"]

    where_sql = " AND ".join(where)

    # Subquery tính tuổi 1 lần rồi gom nhóm bằng UNION ALL (nhanh, rõ)
    sql = f"""
        WITH base AS (
            SELECT
                e.name,
                e.company,
                e.department,
                TIMESTAMPDIFF(YEAR, e.date_of_birth, %(today)s) AS age
            FROM `tabEmployee` e
            WHERE {where_sql} AND e.date_of_birth IS NOT NULL
        )
        (
            SELECT 'Dưới 25 tuổi' AS bucket, COUNT(*) AS count
            FROM base WHERE age < 25
        )
        UNION ALL
        (
            SELECT '25-34 tuổi' AS bucket, COUNT(*) AS count
            FROM base WHERE age BETWEEN 25 AND 34
        )
        UNION ALL
        (
            SELECT '35-44 tuổi' AS bucket, COUNT(*) AS count
            FROM base WHERE age BETWEEN 35 AND 44
        )
        UNION ALL
        (
            SELECT '45-54 tuổi' AS bucket, COUNT(*) AS count
            FROM base WHERE age BETWEEN 45 AND 54
        )
        UNION ALL
        (
            SELECT '55 tuổi trở lên' AS bucket, COUNT(*) AS count
            FROM base WHERE age >= 55
        )
    """
    rows = frappe.db.sql(sql, params, as_dict=True)

    # (tuỳ chọn) đếm thiếu DOB để bạn biết dữ liệu bẩn
    if filters.get("show_unknown_dob"):
        unknown_sql = f"""
            SELECT COUNT(*) FROM `tabEmployee` e
            WHERE {where_sql} AND e.date_of_birth IS NULL
        """
        missing = frappe.db.sql(unknown_sql, params)[0][0]
        rows.append({"bucket": "Không rõ ngày sinh", "count": int(missing)})

    return rows

def make_chart(rows):
    labels = [r["bucket"] for r in rows]
    values = [int(r["count"] or 0) for r in rows]
    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Số nhân sự", "values": values}
            ],
        },
        "type": "bar",   # bar/line/pie tuỳ bạn
        "height": 240,
    }
