from collections import Counter

import frappe
from frappe.utils import getdate, today


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    rows, bucket_counts, bucket_order = get_data(filters)
    chart = make_chart(bucket_counts, bucket_order)
    return columns, rows, None, chart


def get_columns():
    return [
        {"label": "Nhóm tuổi", "fieldname": "bucket", "fieldtype": "Data", "width": 120},
        {"label": "Mã nhân sự", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 130},
        {"label": "Họ và tên", "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {"label": "Ngày sinh", "fieldname": "date_of_birth", "fieldtype": "Date", "width": 110},
        {"label": "Tuổi", "fieldname": "age", "fieldtype": "Int", "width": 80},
        {"label": "Phòng ban", "fieldname": "department_name", "fieldtype": "Data", "width": 200},
        {"label": "Công ty", "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 200},
    ]


def get_data(filters):
    params = {"today": getdate(today())}
    where = []

    status = (filters.get("status") or "").strip()
    if status:
        if status.lower() != "all":
            where.append("e.status = %(status)s")
            params["status"] = status
    else:
        where.append("e.status = %(status)s")
        params["status"] = "Active"

    if filters.get("company"):
        where.append("e.company = %(company)s")
        params["company"] = filters["company"]

    if filters.get("department"):
        where.append("e.department = %(department)s")
        params["department"] = filters["department"]

    where_sql = " AND ".join(where) if where else "1=1"

    show_unknown = bool(filters.get("show_unknown_dob"))
    params["show_unknown"] = 1 if show_unknown else 0

    sql = f"""
        WITH base AS (
            SELECT
                e.name AS employee,
                e.employee_name,
                e.company,
                e.department,
                d.department_name,
                e.date_of_birth,
                CASE
                    WHEN e.date_of_birth IS NULL THEN NULL
                    ELSE TIMESTAMPDIFF(YEAR, e.date_of_birth, %(today)s)
                END AS age
            FROM `tabEmployee` e
            LEFT JOIN `tabDepartment` d ON d.name = e.department
            WHERE {where_sql}
        )
        SELECT
            buckets.employee,
            buckets.employee_name,
            buckets.company,
            buckets.department,
            buckets.department_name,
            buckets.date_of_birth,
            buckets.age,
            buckets.bucket
        FROM (
            SELECT
                base.employee,
                base.employee_name,
                base.company,
                base.department,
                base.department_name,
                base.date_of_birth,
                base.age,
                CASE
                    WHEN base.date_of_birth IS NULL THEN
                        CASE WHEN %(show_unknown)s = 1 THEN 'Không rõ ngày sinh' ELSE NULL END
                    WHEN base.age < 25 THEN 'Dưới 25 tuổi'
                    WHEN base.age BETWEEN 25 AND 34 THEN '25-34 tuổi'
                    WHEN base.age BETWEEN 35 AND 44 THEN '35-44 tuổi'
                    WHEN base.age BETWEEN 45 AND 54 THEN '45-54 tuổi'
                    WHEN base.age >= 55 THEN '55 tuổi trở lên'
                    ELSE NULL
                END AS bucket
            FROM base
            WHERE base.date_of_birth IS NOT NULL OR %(show_unknown)s = 1
        ) buckets
        WHERE buckets.bucket IS NOT NULL
    """
    rows = frappe.db.sql(sql, params, as_dict=True)

    bucket_order = [
        "Dưới 25 tuổi",
        "25-34 tuổi",
        "35-44 tuổi",
        "45-54 tuổi",
        "55 tuổi trở lên",
    ]
    if show_unknown:
        bucket_order.append("Không rõ ngày sinh")

    bucket_counts = Counter()
    order_index = {bucket: index for index, bucket in enumerate(bucket_order)}

    for row in rows:
        if row.get("age") is not None:
            row["age"] = int(row["age"])
        if not row.get("department_name"):
            row["department_name"] = row.get("department")
        bucket = row.get("bucket")
        if bucket:
            bucket_counts[bucket] += 1

    def sort_key(row):
        bucket_idx = order_index.get(row.get("bucket"), len(bucket_order))
        age = row.get("age")
        return (
            bucket_idx,
            age is None,
            age if age is not None else 0,
            (row.get("employee_name") or row.get("employee") or "").lower(),
        )

    rows.sort(key=sort_key)

    return rows, bucket_counts, bucket_order


def make_chart(bucket_counts, bucket_order):
    if not bucket_counts:
        return None

    labels = [bucket for bucket in bucket_order if bucket_counts.get(bucket)]
    if not labels:
        return None

    values = [int(bucket_counts[bucket]) for bucket in labels]
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
