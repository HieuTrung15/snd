# -*- coding: utf-8 -*-
import frappe
from frappe import _

# Thứ tự nhóm viết tắt phòng ban (custom_short_name)
ORDER = [
    "HĐQT", "KS", "CQĐH", "VP HĐQT", "ĐTPT", "QLNNL", "TCKT",
    "TT", "THPC", "CNTT", "VPTD", "39-41", "VCC",
    "Đảng", "CĐ", "Khác"
]

def execute(filters=None):
    filters = filters or {}
    data = get_data(filters)
    return get_columns(), data, None, get_chart(data)


def get_columns():
    return [
        {"label": _("Phòng ban (viết tắt)"), "fieldname": "short_name", "fieldtype": "Data", "width": 140},
        {"label": _("Tên phòng ban"), "fieldname": "department_name", "fieldtype": "Data", "width": 240},
        {"label": _("Số lượng nhân sự"), "fieldname": "employee_count", "fieldtype": "Int", "width": 150},
    ]


def get_data(filters):
    where, params = ["emp.status = 'Active'"], {}

    if filters.get("company"):
        where.append("emp.company = %(company)s")
        params["company"] = filters["company"]

    # Chỉ lấy Department đang hoạt động
    sql = f"""
        SELECT
            d.custom_short_name AS short_name,
            d.department_name   AS department_name,
            COUNT(emp.name)     AS employee_count
        FROM `tabEmployee` emp
        LEFT JOIN `tabDepartment` d ON emp.department = d.name
        WHERE {" AND ".join(where)} AND d.disabled = 0
        GROUP BY d.custom_short_name, d.department_name
    """
    rows = frappe.db.sql(sql, params, as_dict=True)

    # Sắp xếp theo thứ tự ORDER
    order_index = {k: i for i, k in enumerate(ORDER)}
    rows.sort(key=lambda r: order_index.get(r["short_name"], 999))

    # Gộp nhóm "Khác" nếu có phòng ban không có short_name
    other_count = sum(r["employee_count"] for r in rows if not r["short_name"])
    rows = [r for r in rows if r["short_name"]]  # loại dòng rỗng
    if other_count:
        rows.append({"short_name": "Khác", "department_name": "Khác", "employee_count": other_count})

    return rows


def get_chart(rows):
    labels = [r["short_name"] for r in rows]
    values = [r["employee_count"] for r in rows]

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "name": _("Nhân sự"),
                    "values": values,
                    "chartType": "bar",
                    "color": "#3288f1"  # xanh dương
                }
            ]
        },
        "type": "bar",
        "height": 280,
        "colors": ["#3288f1"],
        "barOptions": {"spaceRatio": 0.4}
    }
