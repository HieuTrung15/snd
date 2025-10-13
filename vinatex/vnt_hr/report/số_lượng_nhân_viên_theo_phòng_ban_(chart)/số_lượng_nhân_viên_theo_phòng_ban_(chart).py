# apps/vinatex/vinatex/vnt_hr/report/tong_hop_nhan_su_theo_phong_ban/tong_hop_nhan_su_theo_phong_ban.py
import frappe
from frappe import _

ORDER = [
    "HĐQT","KS","CQĐH","VP HĐQT","ĐTPT","QLNNL","TCKT",
    "TT","THPC","CNTT","VPTD","39-41","VCC","Đảng","CĐ","Khác"
]

def execute(filters=None):
    filters = filters or {}
    rows = get_data(filters)
    return get_columns(), rows, None, get_chart(rows)

def get_columns():
    return [
        {"label": _("Phòng ban (viết tắt)"), "fieldname": "short_name", "fieldtype": "Data", "width": 140},
        {"label": _("Số lượng nhân sự"), "fieldname": "employee_count", "fieldtype": "Int", "width": 150},
    ]

def get_data(filters):
    conds, params = ["emp.status = 'Active'"], {}
    if filters.get("company"):
        conds.append("emp.company = %(company)s")
        params["company"] = filters["company"]

    sql = """
        SELECT
            COALESCE(NULLIF(TRIM(d.custom_short_name), ''), 'Khác') AS short_name,
            COUNT(emp.name) AS employee_count
        FROM `tabEmployee` emp
        INNER JOIN `tabDepartment` d
            ON d.name = emp.department AND d.disabled = 0
        WHERE {cond}
        GROUP BY short_name
        ORDER BY FIELD(short_name, {order_list}), short_name
    """.format(
        cond=" AND ".join(conds),
        order_list=", ".join(frappe.db.escape(x) for x in ORDER)
    )

    return frappe.db.sql(sql, params, as_dict=True)

def get_chart(rows):
    return {
        "data": {
            "labels": [r["short_name"] for r in rows],
            "datasets": [{
                "name": _("Nhân sự"),
                "values": [r["employee_count"] for r in rows],
                "chartType": "bar",
                "color": "#3288f1"
            }]
        },
        "type": "bar",
        "height": 280,
        "colors": ["#3288f1"],
        "barOptions": {"spaceRatio": 0.4}
    }
