# -*- coding: utf-8 -*-
import frappe
from frappe import _

# Thứ tự hiển thị, nhưng CHỈ hiện những nhóm có dữ liệu
ORDERED_GROUPS = [
    "Người quản lý",
    "LĐ cấp trung",
    "CV/NV",
    "KGKHĐLĐ",
]

def execute(filters=None):
    filters = filters or {}
    rows = get_data(filters)

    # sắp theo ORDERED_GROUPS, bỏ nhóm count=0 (SQL đã loại)
    order = {g: i for i, g in enumerate(ORDERED_GROUPS)}
    rows.sort(key=lambda r: order.get(r["designation_group"], 999))

    return get_columns(), rows, None, get_chart_data(rows)


def get_columns():
    return [
        {"label": _("Nhóm chức danh"), "fieldname": "designation_group", "fieldtype": "Data", "width": 260},
        {"label": _("Số lượng nhân sự"), "fieldname": "employee_count", "fieldtype": "Int", "width": 140},
    ]


def get_data(filters):
    params = {}
    conds = ["employee.status = 'Active'"]
    if filters.get("company"):
        conds.append("employee.company = %(company)s")
        params["company"] = filters.get("company")

    # Nhãn gốc trong DB (Link)
    allowed_raw = [
        "Người quản lý",
        "Lãnh đạo cấp trung",
        "Chuyên viên, Nhân viên",
        "Không giao kết HĐLĐ",
    ]
    in_ph = ", ".join([f"%(g{i})s" for i in range(len(allowed_raw))])
    for i, v in enumerate(allowed_raw):
        params[f"g{i}"] = v

    # Map sang nhãn rút gọn để hiển thị/sort
    display_expr = """
        CASE employee.custom_designation_group
            WHEN 'Người quản lý'        THEN 'Người quản lý'
            WHEN 'Lãnh đạo cấp trung'   THEN 'LĐ cấp trung'
            WHEN 'Chuyên viên, Nhân viên' THEN 'CV/NV'
            WHEN 'Không giao kết HĐLĐ'  THEN 'KGKHĐLĐ'
        END
    """

    sql = f"""
        SELECT
            {display_expr} AS designation_group,
            COUNT(*) AS employee_count
        FROM `tabEmployee` AS employee
        WHERE {" AND ".join(conds)}
          AND employee.custom_designation_group IN ({in_ph})
        GROUP BY {display_expr}
    """
    return frappe.db.sql(sql, params, as_dict=True)



def get_chart_data(rows):
    if not rows: 
        return None
    return {
        "data": {
            "labels": [r["designation_group"] for r in rows],
            "datasets": [{"name": _("Nhân sự"), "values": [int(r["employee_count"] or 0) for r in rows]}],
        },
        "type": "bar",
        "height": 320,
    }
