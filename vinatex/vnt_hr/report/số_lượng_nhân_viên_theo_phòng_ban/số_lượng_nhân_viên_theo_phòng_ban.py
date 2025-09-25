# -*- coding: utf-8 -*-
# Path gợi ý: your_app/your_app/report/employees_by_department/employees_by_department.py

import frappe
from frappe import _

def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    chart = get_chart(data)
    report_summary = get_report_summary(data)

    return columns, data, None, chart, report_summary


def get_columns():
    return [
        {
            "fieldname": "department",
            "label": _("Department"),
            "fieldtype": "Link",
            "options": "Department",
            "width": 260,
        },
        {
            "fieldname": "total",
            "label": _("Employees"),
            "fieldtype": "Int",
            "width": 120,
        },
    ]


def get_data(filters):
    # Xây filters cho Employee
    emp_filters = {}
    if filters.get("company"):
        emp_filters["company"] = filters.company
    if filters.get("status"):
        emp_filters["status"] = filters.status  

    if filters.get("department"):
        emp_filters["department"] = filters.department

    # Count theo department (kể cả None)
    # Dùng SQL để gom nhóm cả các bản ghi department is null
    conditions, values = build_conditions(emp_filters)

    query = f"""
        SELECT
            COALESCE(d.department_name, '{_("(No Department)")}') AS department,
            COALESCE(d.custom_short_name, '{_("(No Department)")}') AS short_name,
            COUNT(e.name) AS total
        FROM `tabEmployee` e
        Left JOIN `tabDepartment` d ON e.department = d.name
        {('WHERE ' + ' AND '.join(conditions)) if conditions else ''}
        GROUP BY department, short_name
        ORDER BY total DESC, department ASC
    """

    rows = frappe.db.sql(query, values, as_dict=True)
    return [{"department": r["department"],"short_name":r["short_name"], "total": int(r["total"])} for r in rows]


def build_conditions(emp_filters):
    conditions, values = [], []
    if emp_filters.get("company"):
        conditions.append("e.company = %s")
        values.append(emp_filters["company"])
    if emp_filters.get("status"):
        conditions.append("e.status = %s")
        values.append(emp_filters["status"])
    if emp_filters.get("department"):
        conditions.append("e.department = %s")
        values.append(emp_filters["department"])
    return conditions, values


def get_chart(data):
    # Chỉ lấy 10 dòng đầu để vẽ chart
    top10 = data[:10]

    # Luôn lấy short_name làm label
    labels = [d["short_name"] for d in top10]
    values = [d["total"] for d in top10]

    return {
        "data": {
            "labels": labels,
            "datasets": [{"name": _("Employees"), "values": values}],
        },
        "type": "bar",  # hoặc "pie" nếu thích
        "axis_options": {"x_axis_mode": "tick", "x_is_series": False},
        "height": 300,
    }




def get_report_summary(data):
    total_employees = sum(d["total"] for d in data) if data else 0
    dept_count = len(data)
    max_row = max(data, key=lambda x: x["total"]) if data else None

    summary = [
        {
            "label": _("Tổng số nhân sự"),
            "value": total_employees,
            "indicator": "green",
        },
        {
            "label": _("Tổng số phòng ban"),
            "value": dept_count,
            "indicator": "blue",
        },
    ]

    if max_row:
        summary.append(
            {
                "label": _("Đơn vị nhiều nhân sự nhất"),
                "value": f'{max_row["department"]} ({max_row["total"]})',
                "indicator": "orange",
            }
        )

    return summary
